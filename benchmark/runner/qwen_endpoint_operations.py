from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .common import REPOSITORY_ROOT
from .paid_stage_meter import CombinedPaidStageMeter, PaidStageMeterError, QWEN
from .paid_stage_error_policy import POLICY_PATH, validate_paid_stage_error_policy
from .qwen_deployment_candidate import validate_qwen_deployment_candidate


OPERATIONS_CONFIG_PATH = (
    REPOSITORY_ROOT / "benchmark" / "config" / "qwen_endpoint_operations.json"
)
CANDIDATE_PATH = (
    REPOSITORY_ROOT / "benchmark" / "config" / "qwen_deployment.candidate.json"
)
EVIDENCE_SCHEMA_VERSION = "1.0.0"
EXPECTED_OPERATIONS_CONFIG_SHA256 = (
    "820f8948f37e8ce2e167475a5d7fdb056d9bc6fe4c7bf91b4737660d4c5353eb"
)
TERMINAL_FAILURE_STATUSES = {"failed", "updateFailed"}
READY_STATUS = "running"
IN_PROGRESS_STATUSES = {"pending", "initializing", "updating"}
PAUSED_STATUS = "paused"
SCALED_TO_ZERO_STATUS = "scaledToZero"
SDK_CREATE_PARAMETERS = {
    "name", "repository", "framework", "accelerator", "instance_size",
    "instance_type", "region", "vendor", "min_replica", "max_replica",
    "scale_to_zero_timeout", "revision", "task", "custom_image",
    "container_args", "type", "namespace", "token",
}


class QwenEndpointOperationError(RuntimeError):
    """An Endpoint lifecycle operation failed closed."""


@dataclass(frozen=True)
class EndpointState:
    status: str
    url: str | None = None


class EndpointManagementClient(Protocol):
    package_version: str

    def create(self, *, name: str, namespace: str, request: Mapping[str, Any]) -> EndpointState: ...

    def get(self, *, name: str, namespace: str) -> EndpointState: ...

    def resume(self, *, name: str, namespace: str) -> EndpointState: ...

    def scale_to_zero(self, *, name: str, namespace: str) -> EndpointState: ...

    def health(self, *, endpoint_url: str, route: str, timeout_seconds: float) -> int: ...


class HuggingFaceHubEndpointClient:
    """Lazy, exact-version adapter around the official management SDK."""

    def __init__(self, *, token: str | None, expected_version: str) -> None:
        self._token = None if token is None else validate_huggingface_token(token)
        self._expected_version = expected_version
        self._api: Any = None
        self.package_version = "not-loaded"

    def _load(self) -> Any:
        if not self._token:
            raise QwenEndpointOperationError("HF_TOKEN is absent")
        try:
            actual = importlib.metadata.version("huggingface_hub")
        except importlib.metadata.PackageNotFoundError as error:
            raise QwenEndpointOperationError(
                f"huggingface_hub=={self._expected_version} is not installed"
            ) from error
        if actual != self._expected_version:
            raise QwenEndpointOperationError(
                f"huggingface_hub version mismatch: expected {self._expected_version}"
            )
        self.package_version = actual
        if self._api is None:
            from huggingface_hub import HfApi

            self._api = HfApi(token=self._token)
        return self._api

    def create(self, *, name: str, namespace: str, request: Mapping[str, Any]) -> EndpointState:
        endpoint = self._load().create_inference_endpoint(
            name=name, namespace=namespace, token=self._token, **dict(request)
        )
        return _state_from_sdk(endpoint)

    def get(self, *, name: str, namespace: str) -> EndpointState:
        endpoint = self._load().get_inference_endpoint(
            name=name, namespace=namespace, token=self._token
        )
        return _state_from_sdk(endpoint)

    def resume(self, *, name: str, namespace: str) -> EndpointState:
        endpoint = self._load().resume_inference_endpoint(
            name=name, namespace=namespace, running_ok=True, token=self._token
        )
        return _state_from_sdk(endpoint)

    def scale_to_zero(self, *, name: str, namespace: str) -> EndpointState:
        endpoint = self._load().scale_to_zero_inference_endpoint(
            name=name, namespace=namespace, token=self._token
        )
        return _state_from_sdk(endpoint)

    def health(self, *, endpoint_url: str, route: str, timeout_seconds: float) -> int:
        self._load()
        url = endpoint_url.rstrip("/") + route
        request = Request(url, method="GET", headers={"Authorization": f"Bearer {self._token}"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status)
        except HTTPError as error:
            return int(error.code)


class QwenEndpointOperator:
    def __init__(
        self,
        *,
        meter: CombinedPaidStageMeter,
        client: EndpointManagementClient,
        endpoint_name: str,
        namespace: str,
        evidence_path: str | Path,
        operations_config_path: str | Path = OPERATIONS_CONFIG_PATH,
        candidate_path: str | Path = CANDIDATE_PATH,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.meter = meter
        self.client = client
        self.endpoint_name = _identifier(endpoint_name, "endpoint_name")
        self.namespace = _identifier(namespace, "namespace")
        self.evidence_path = Path(evidence_path).resolve()
        self.operations_config_path = Path(operations_config_path).resolve()
        self.candidate_path = Path(candidate_path).resolve()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleeper
        self._monotonic = monotonic
        self.config, self.candidate = _load_and_validate_configuration(
            self.operations_config_path, self.candidate_path
        )
        required_name = self.candidate["deployment"]["endpoint_strategy"][
            "required_name"
        ]
        if self.endpoint_name != required_name:
            raise QwenEndpointOperationError(
                f"endpoint_name must equal the reviewed r4 name {required_name}"
            )
        self.create_request = _build_create_request(self.config, self.candidate)

    def create(self, *, action_id: str) -> dict[str, Any]:
        def create_operation() -> EndpointState:
            return _require_nonfailed_state(
                self.client.create(
                    name=self.endpoint_name,
                    namespace=self.namespace,
                    request=self.create_request,
                )
            )

        return self._run(
            operation="create",
            action_id=action_id,
            function=lambda: self.meter.execute_qwen_runtime_start(
                action_id=action_id,
                hourly_rate_usd=self.candidate["deployment"]["hardware"][
                    "public_listed_hourly_rate_usd"
                ],
                operation=create_operation,
            ),
        )

    def start(self, *, action_id: str, phase: str = "live_gate") -> dict[str, Any]:
        phase = _phase(phase)

        def start_operation() -> EndpointState:
            state = self.client.get(name=self.endpoint_name, namespace=self.namespace)
            if state.status == PAUSED_STATUS:
                return _require_nonfailed_state(
                    self.client.resume(name=self.endpoint_name, namespace=self.namespace)
                )
            if state.status in {READY_STATUS, *IN_PROGRESS_STATUSES}:
                return state
            if state.status == SCALED_TO_ZERO_STATUS:
                raise QwenEndpointOperationError(
                    "request-based wake from scaledToZero is prohibited during live_gate"
                )
            raise QwenEndpointOperationError(
                "Endpoint status cannot be started without user feedback"
            )

        if phase == "pilot":
            function: Callable[[], Any] = lambda: self._pilot_start(action_id)
        else:
            function = lambda: self.meter.execute_qwen_runtime_start(
                action_id=action_id,
                hourly_rate_usd=self.candidate["deployment"]["hardware"][
                    "public_listed_hourly_rate_usd"
                ],
                operation=start_operation,
            )
        return self._run(
            operation="start",
            action_id=action_id,
            function=function,
        )

    def _pilot_start(self, action_id: str) -> Any:
        self.meter.start_qwen_runtime(
            action_id,
            hourly_rate_usd=self.candidate["deployment"]["hardware"][
                "public_listed_hourly_rate_usd"
            ],
        )
        try:
            state = self.client.get(name=self.endpoint_name, namespace=self.namespace)
            if state.status == PAUSED_STATUS:
                return _require_nonfailed_state(
                    self.client.resume(name=self.endpoint_name, namespace=self.namespace)
                )
            if state.status in {READY_STATUS, *IN_PROGRESS_STATUSES}:
                return state
            if state.status == SCALED_TO_ZERO_STATUS:
                return self._trigger_pilot_wake(action_id, state)
            _require_nonfailed_state(state)
            raise QwenEndpointOperationError(
                "Endpoint status cannot be started without user feedback"
            )
        except BaseException:
            ledger = self.meter.snapshot()
            if ledger["status"] == "ACTIVE":
                self.meter.record_interface_failure(
                    f"{action_id}:pilot_start_failure", QWEN
                )
            raise

    def _trigger_pilot_wake(
        self, action_id: str, state: EndpointState
    ) -> dict[str, Any]:
        if state.url is None:
            raise QwenEndpointOperationError(
                "scaledToZero Endpoint omitted the URL required for pilot wake"
            )
        _validate_endpoint_url(
            state.url,
            self.config["lifecycle_policy"]["allowed_endpoint_host_suffix"],
        )
        attempt_id = f"{action_id}:wake:attempt:1"
        ticket = self.meter.reserve_action(
            attempt_id, QWEN, "0", require_qwen_runtime=True
        )
        try:
            code = self.client.health(
                endpoint_url=state.url,
                route=self.config["lifecycle_policy"]["pilot_wake_trigger_route"],
                timeout_seconds=30,
            )
        except BaseException as error:
            retryable = _retryable_pilot_exception(error)
            self.meter.settle_action(
                ticket,
                outcome=(
                    "retryable_request_failure" if retryable else "interface_failure"
                ),
                actual_increment_usd="0",
                stop_stage_on_failure=not retryable,
            )
            if not retryable:
                raise
            return {
                "state": EndpointState("pending", state.url),
                "wake_status": None,
                "wake_exception_type": type(error).__name__,
            }
        success_code = self.config["lifecycle_policy"]["health_success_status"]
        retryable_statuses = set(
            self.config["lifecycle_policy"]["pilot_wake_retryable_http_statuses"]
        )
        if code == success_code:
            self.meter.settle_action(
                ticket,
                outcome="success",
                actual_increment_usd="0",
                stop_stage_on_failure=False,
            )
            return {
                "state": EndpointState(READY_STATUS, state.url),
                "wake_status": code,
            }
        retryable = code in retryable_statuses
        self.meter.settle_action(
            ticket,
            outcome=("retryable_provider_failure" if retryable else "provider_failure"),
            actual_increment_usd="0",
            stop_stage_on_failure=not retryable,
        )
        if not retryable:
            raise QwenEndpointOperationError(f"pilot wake returned HTTP {code}")
        return {
            "state": EndpointState("pending", state.url),
            "wake_status": code,
        }

    def status(self, *, action_id: str) -> dict[str, Any]:
        def operation() -> EndpointState:
            try:
                return _require_nonfailed_state(
                    self.client.get(name=self.endpoint_name, namespace=self.namespace)
                )
            except BaseException:
                self.meter.record_interface_failure(action_id, QWEN)
                raise

        return self._run(operation="status", action_id=action_id, function=operation)

    def wait_ready(
        self,
        *,
        action_id: str,
        timeout_seconds: float,
        poll_interval_seconds: float,
        phase: str = "live_gate",
    ) -> dict[str, Any]:
        phase = _phase(phase)
        if timeout_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("wait durations must be positive")

        def operation() -> EndpointState:
            start = self._monotonic()
            while True:
                state = self.client.get(name=self.endpoint_name, namespace=self.namespace)
                if state.status == READY_STATUS:
                    return state
                if state.status in TERMINAL_FAILURE_STATUSES:
                    raise QwenEndpointOperationError(
                        "Endpoint entered a failed status; no replacement was created"
                    )
                allowed_waiting = set(IN_PROGRESS_STATUSES)
                if phase == "pilot":
                    allowed_waiting.add(SCALED_TO_ZERO_STATUS)
                if state.status not in allowed_waiting:
                    raise QwenEndpointOperationError(
                        "Endpoint entered an unexpected non-ready status"
                    )
                if self._monotonic() - start >= timeout_seconds:
                    raise QwenEndpointOperationError("Endpoint readiness deadline expired")
                self._sleep(min(poll_interval_seconds, timeout_seconds))

        def guarded() -> EndpointState:
            return self.meter.execute(
                action_id=action_id,
                provider=QWEN,
                projected_increment_usd="0",
                operation=operation,
                actual_increment=lambda _result: "0",
                require_qwen_runtime=True,
            )

        return self._run(operation="wait-ready", action_id=action_id, function=guarded)

    def health(
        self,
        *,
        action_id: str,
        timeout_seconds: float,
        phase: str = "live_gate",
    ) -> dict[str, Any]:
        phase = _phase(phase)
        if timeout_seconds <= 0:
            raise ValueError("health timeout must be positive")
        latest_status: int | None = None

        def operation() -> dict[str, Any]:
            nonlocal latest_status
            state = self.client.get(name=self.endpoint_name, namespace=self.namespace)
            if state.status != READY_STATUS or state.url is None:
                raise QwenEndpointOperationError("health check requires provider status running and a URL")
            _validate_endpoint_url(
                state.url,
                self.config["lifecycle_policy"]["allowed_endpoint_host_suffix"],
            )
            code = self.client.health(
                endpoint_url=state.url,
                route=self.config["lifecycle_policy"]["health_route"],
                timeout_seconds=timeout_seconds,
            )
            latest_status = code
            return {"state": state, "health_status": code}

        def guarded() -> dict[str, Any]:
            nonlocal latest_status
            policy = _load_paid_policy()["phases"][phase]
            maximum = policy["maximum_http_attempts_per_logical_request"]
            retryable_statuses = set(policy.get("retryable_http_statuses", []))
            delays = policy.get("retry_delays_seconds", [])
            for attempt in range(1, maximum + 1):
                latest_status = None
                attempt_id = action_id if phase == "live_gate" else f"{action_id}:attempt:{attempt}"
                final_attempt = attempt == maximum
                try:
                    result = self.meter.execute(
                        action_id=attempt_id,
                        provider=QWEN,
                        projected_increment_usd="0",
                        operation=operation,
                        actual_increment=lambda _result: "0",
                        response_succeeded=lambda item: item["health_status"]
                        == self.config["lifecycle_policy"]["health_success_status"],
                        require_qwen_runtime=True,
                        operation_failure_stops_stage=lambda error: (
                            phase == "live_gate"
                            or final_attempt
                            or not _retryable_pilot_exception(error)
                        ),
                        response_failure_stops_stage=lambda item: (
                            phase == "live_gate"
                            or final_attempt
                            or item["health_status"] not in retryable_statuses
                        ),
                    )
                except BaseException as error:
                    if (
                        phase == "pilot"
                        and not final_attempt
                        and _retryable_pilot_exception(error)
                    ):
                        self._sleep(delays[attempt - 1])
                        continue
                    if latest_status is not None:
                        raise QwenEndpointOperationError(
                            f"health check returned HTTP {latest_status}"
                        ) from error
                    raise
                if result["health_status"] == self.config["lifecycle_policy"][
                    "health_success_status"
                ]:
                    return result
                if (
                    phase == "pilot"
                    and not final_attempt
                    and result["health_status"] in retryable_statuses
                ):
                    self._sleep(delays[attempt - 1])
                    continue
                raise QwenEndpointOperationError(
                    f"health check returned HTTP {result['health_status']}"
                )
            raise AssertionError("unreachable health retry state")

        return self._run(operation="health", action_id=action_id, function=guarded)

    def scale_to_zero(self, *, action_id: str) -> dict[str, Any]:
        def operation() -> EndpointState:
            state = self.client.scale_to_zero(
                name=self.endpoint_name, namespace=self.namespace
            )
            if state.status != SCALED_TO_ZERO_STATUS:
                state = self.client.get(name=self.endpoint_name, namespace=self.namespace)
            if state.status != SCALED_TO_ZERO_STATUS:
                raise QwenEndpointOperationError("scale-to-zero was not positively confirmed")
            return state

        return self._run(
            operation="scale-to-zero",
            action_id=action_id,
            function=lambda: self.meter.execute_qwen_runtime_stop(
                action_id=action_id, operation=operation
            ),
        )

    def _run(
        self, *, operation: str, action_id: str, function: Callable[[], Any]
    ) -> dict[str, Any]:
        action_id = _action_id(action_id)
        started_at = self._timestamp()
        before = _safe_ledger_summary(self.meter)
        outcome = "failure"
        result: Any = None
        failure: dict[str, Any] | None = None
        try:
            result = function()
            outcome = "success"
            return _public_result(result)
        except BaseException as error:
            failure = _failure_summary(error)
            raise QwenEndpointOperationError(
                f"{operation} failed closed; inspect {self.evidence_path.name}"
            ) from error
        finally:
            finished_at = self._timestamp()
            evidence = {
                "schema_version": EVIDENCE_SCHEMA_VERSION,
                "operation": operation,
                "action_id": action_id,
                "outcome": outcome,
                "started_at": started_at,
                "finished_at": finished_at,
                "endpoint_name": self.endpoint_name,
                "namespace_sha256": hashlib.sha256(self.namespace.encode("utf-8")).hexdigest(),
                "candidate_id": self.config["candidate_id"],
                "candidate_configuration_sha256": self.config[
                    "candidate_configuration_sha256"
                ],
                "operations_configuration_sha256": self.config[
                    "configuration_sha256"
                ],
                "operator_implementation_sha256": _implementation_sha256(),
                "management_client": {
                    "package": self.config["management_client"]["package"],
                    "expected_version": self.config["management_client"]["version"],
                    "observed_version": self.client.package_version,
                },
                "create_request_sha256": _canonical_sha256(self.create_request),
                "ledger_before": before,
                "ledger_after": _safe_ledger_summary(self.meter),
                "result": _evidence_result(result),
                "failure": failure,
            }
            evidence["evidence_sha256"] = _canonical_sha256(evidence)
            _atomic_create_json(self.evidence_path, evidence)

    def _timestamp(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            raise QwenEndpointOperationError("operator clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_operation_evidence(value: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version", "operation", "action_id", "outcome", "started_at",
        "finished_at", "endpoint_name", "namespace_sha256", "candidate_id",
        "candidate_configuration_sha256", "operations_configuration_sha256",
        "operator_implementation_sha256", "management_client",
        "create_request_sha256", "ledger_before",
        "ledger_after", "result", "failure", "evidence_sha256",
    }
    if set(value) != required:
        return ["evidence fields mismatch"]
    if value.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        issues.append("schema_version mismatch")
    if value.get("outcome") not in {"success", "failure"}:
        issues.append("outcome is invalid")
    if value.get("outcome") == "success" and value.get("failure") is not None:
        issues.append("successful evidence cannot contain failure")
    if value.get("outcome") == "failure" and not isinstance(value.get("failure"), Mapping):
        issues.append("failed evidence requires a failure summary")
    if value.get("evidence_sha256") != _canonical_sha256(value):
        issues.append("evidence_sha256 mismatch")
    if value.get("operator_implementation_sha256") != _implementation_sha256():
        issues.append("operator implementation binding mismatch")
    try:
        config = json.loads(OPERATIONS_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        issues.append("current operations configuration cannot be read")
    else:
        if value.get("operations_configuration_sha256") != config.get(
            "configuration_sha256"
        ):
            issues.append("operations configuration binding mismatch")
        if value.get("candidate_configuration_sha256") != config.get(
            "candidate_configuration_sha256"
        ):
            issues.append("candidate configuration binding mismatch")
    return issues


def configuration_report(*, check_sdk: bool) -> dict[str, Any]:
    config, candidate = _load_and_validate_configuration(
        OPERATIONS_CONFIG_PATH, CANDIDATE_PATH
    )
    request = _build_create_request(config, candidate)
    report: dict[str, Any] = {
        "valid": True,
        "candidate_id": config["candidate_id"],
        "candidate_configuration_sha256": config["candidate_configuration_sha256"],
        "paid_stage_error_policy_sha256": config[
            "paid_stage_error_policy_sha256"
        ],
        "operations_configuration_sha256": config["configuration_sha256"],
        "operator_implementation_sha256": _implementation_sha256(),
        "create_request_sha256": _canonical_sha256(request),
        "management_client": {
            "package": config["management_client"]["package"],
            "expected_version": config["management_client"]["version"],
            "installed_version": None,
            "interface_valid": None,
        },
        "token_environment_variable": config["management_client"][
            "token_environment_variable"
        ],
        "token_present": bool(
            os.environ.get(config["management_client"]["token_environment_variable"])
        ),
        "network_called": False,
        "cost_incurred": False,
    }
    if check_sdk:
        expected = config["management_client"]["version"]
        try:
            actual = importlib.metadata.version(config["management_client"]["package"])
        except importlib.metadata.PackageNotFoundError as error:
            raise QwenEndpointOperationError(
                f"huggingface_hub=={expected} is not installed"
            ) from error
        if actual != expected:
            raise QwenEndpointOperationError(
                f"huggingface_hub version mismatch: expected {expected}, found {actual}"
            )
        from huggingface_hub import HfApi

        parameters = set(inspect.signature(HfApi.create_inference_endpoint).parameters)
        missing = SDK_CREATE_PARAMETERS - parameters
        if missing:
            raise QwenEndpointOperationError(
                f"huggingface_hub create interface lacks: {sorted(missing)}"
            )
        report["management_client"]["installed_version"] = actual
        report["management_client"]["interface_valid"] = True
    return report


def credential_preflight_report(
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = os.environ if environ is None else environ
    token_name = "HF_TOKEN"
    token = environment.get(token_name)
    if token is None:
        raise QwenEndpointOperationError("HF_TOKEN is absent")
    validate_huggingface_token(token)
    return {
        "valid": True,
        "token_environment_variable": token_name,
        "token_present": True,
        "printable_ascii": True,
        "network_called": False,
        "cost_incurred": False,
    }


def _load_and_validate_configuration(
    operations_path: Path, candidate_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads(operations_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if validate_qwen_deployment_candidate(candidate):
        raise QwenEndpointOperationError("Qwen deployment candidate validation failed")
    expected_top = {
        "schema_version", "status", "candidate_id",
        "candidate_configuration_sha256", "paid_stage_error_policy_sha256",
        "management_client",
        "create_request", "lifecycle_policy", "configuration_sha256",
    }
    if set(config) != expected_top:
        raise QwenEndpointOperationError("operations configuration fields mismatch")
    if config.get("status") != "FROZEN" or config.get("schema_version") != "1.0.0":
        raise QwenEndpointOperationError("Qwen Endpoint operations config is not frozen")
    if config.get("management_client") != {
        "package": "huggingface_hub",
        "version": "1.24.0",
        "token_environment_variable": "HF_TOKEN",
    }:
        raise QwenEndpointOperationError("management client boundary mismatch")
    policy = _load_paid_policy()
    if config.get("paid_stage_error_policy_sha256") != policy["policy_sha256"]:
        raise QwenEndpointOperationError("paid-stage error policy binding mismatch")
    if config.get("create_request") != {
        "framework": "custom",
        "task": "text-generation",
        "vendor": "aws",
        "region": "us-east-1",
        "type": "authenticated",
        "accelerator": "gpu",
        "instance_type": "nvidia-l4",
        "instance_size": "x1",
        "min_replica": 0,
        "max_replica": 1,
        "scale_to_zero_timeout": 15,
    }:
        raise QwenEndpointOperationError("create request boundary mismatch")
    if config.get("lifecycle_policy") != {
        "start_meter_before_create_or_resume": True,
        "stop_meter_only_after_scaled_to_zero_is_confirmed": True,
        "health_requires_running_status_and_active_meter": True,
        "health_route": "/health",
        "health_success_status": 200,
        "allowed_endpoint_host_suffix": ".endpoints.huggingface.cloud",
        "scaled_to_zero_status": "scaledToZero",
        "automatic_delete_recreate_or_substitution": False,
        "scaled_to_zero_request_wake": "LIVE_GATE_PROHIBITED_PILOT_TRANSIENT_WAKE_ALLOWED",
        "pilot_wake_trigger_route": "/health",
        "pilot_wake_retryable_http_statuses": [408, 409, 425, 429, 500, 502, 503, 504],
        "failed_status_requires_user_feedback": True,
    }:
        raise QwenEndpointOperationError("lifecycle policy boundary mismatch")
    if config.get("candidate_id") != candidate.get("candidate_id"):
        raise QwenEndpointOperationError("operations config candidate binding mismatch")
    if config.get("candidate_configuration_sha256") != candidate.get(
        "candidate_configuration_sha256"
    ):
        raise QwenEndpointOperationError("operations config candidate hash mismatch")
    if config.get("configuration_sha256") != _canonical_sha256(config):
        raise QwenEndpointOperationError("operations configuration hash mismatch")
    if config.get("configuration_sha256") != EXPECTED_OPERATIONS_CONFIG_SHA256:
        raise QwenEndpointOperationError("operations configuration is not the reviewed version")
    return config, candidate


def _build_create_request(config: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    deployment = candidate["deployment"]
    runtime = deployment["runtime"]
    request = dict(config["create_request"])
    request.update(
        {
            "repository": deployment["model"]["repository"],
            "revision": deployment["model"]["repository_commit"],
            "custom_image": {
                "url": runtime["container_image_uri"],
                "healthRoute": runtime["health_route"],
                "port": runtime["container_port"],
            },
            "container_args": list(runtime["container_arguments"]),
        }
    )
    return request


def _state_from_sdk(endpoint: Any) -> EndpointState:
    status = getattr(endpoint, "status", None)
    if hasattr(status, "value"):
        status = status.value
    if not isinstance(status, str) or not status:
        raise QwenEndpointOperationError("provider response omitted Endpoint status")
    url = getattr(endpoint, "url", None)
    if url is not None and not isinstance(url, str):
        raise QwenEndpointOperationError("provider response returned a malformed URL")
    return EndpointState(status=status, url=url)


def _require_nonfailed_state(state: EndpointState) -> EndpointState:
    if state.status in TERMINAL_FAILURE_STATUSES:
        raise QwenEndpointOperationError(
            "Endpoint entered a failed status; automatic replacement is prohibited"
        )
    return state


def _validate_endpoint_url(value: str, allowed_suffix: str) -> None:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise QwenEndpointOperationError("Endpoint URL violates the authenticated TLS boundary")
    if not host.endswith(allowed_suffix) or host == allowed_suffix.lstrip("."):
        raise QwenEndpointOperationError("Endpoint URL host is outside the frozen provider suffix")
    if parsed.path not in {"", "/"}:
        raise QwenEndpointOperationError("Endpoint base URL contains an unexpected path")


def _safe_ledger_summary(meter: CombinedPaidStageMeter) -> dict[str, Any]:
    try:
        state = meter.snapshot()
        return {
            "status": state["status"],
            "stop_reason": state["stop_reason"],
            "state_sha256": state["state_sha256"],
            "qwen_runtime_active": state["qwen_runtime"]["active"],
            "qwen_runtime_started_at": state["qwen_runtime"]["started_at"],
            "qwen_local_increment_estimate_usd": state[
                "local_increment_estimate_usd"
            ][QWEN],
        }
    except BaseException as error:
        return {"unavailable": True, "error_type": type(error).__name__}


def _public_result(value: Any) -> dict[str, Any]:
    if isinstance(value, EndpointState):
        return {"status": value.status, "url_sha256": _url_sha(value.url)}
    if isinstance(value, Mapping) and isinstance(value.get("state"), EndpointState):
        state = value["state"]
        result = {
            "status": state.status,
            "url_sha256": _url_sha(state.url),
            "health_status": value.get("health_status"),
        }
        if "wake_status" in value:
            result["wake_status"] = value.get("wake_status")
        if "wake_exception_type" in value:
            result["wake_exception_type"] = value.get("wake_exception_type")
        return result
    return {"completed": True}


def _evidence_result(value: Any) -> dict[str, Any] | None:
    return None if value is None else _public_result(value)


def _url_sha(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode("utf-8")).hexdigest()


def _failure_summary(error: BaseException) -> dict[str, Any]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    message = " | ".join(str(item) for item in chain)
    status = None
    match = re.search(r"(?:HTTP|status(?: code)?)\s*(\d{3})", message, re.IGNORECASE)
    if match:
        status = int(match.group(1))
    return {
        "error_type": type(error).__name__,
        "root_error_type": type(chain[-1]).__name__,
        "http_status": status,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "requires_user_feedback": True,
    }


def _load_paid_policy() -> dict[str, Any]:
    try:
        value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QwenEndpointOperationError("paid-stage error policy cannot be read") from error
    issues = validate_paid_stage_error_policy(value)
    if issues:
        raise QwenEndpointOperationError(
            f"paid-stage error policy is invalid: {'; '.join(issues)}"
        )
    return value


def _phase(value: str) -> str:
    if value not in {"live_gate", "pilot"}:
        raise ValueError("phase must be live_gate or pilot")
    return value


def _retryable_pilot_exception(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: list[BaseException] = []
    while current is not None and current not in visited:
        visited.append(current)
        if isinstance(current, (TimeoutError, ConnectionError, URLError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _canonical_sha256(value: Any) -> str:
    if isinstance(value, Mapping) and "evidence_sha256" in value:
        value = {key: item for key, item in value.items() if key != "evidence_sha256"}
    if isinstance(value, Mapping) and "configuration_sha256" in value:
        value = {key: item for key, item in value.items() if key != "configuration_sha256"}
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _implementation_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _atomic_create_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _output_lock(path):
        if path.exists():
            raise QwenEndpointOperationError("operation evidence already exists")
        encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


@contextmanager
def _output_lock(path: Path) -> Iterator[None]:
    lock = path.with_name(f"{path.name}.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise QwenEndpointOperationError("operation evidence is locked") from error
    try:
        os.close(descriptor)
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty without surrounding whitespace")
    if len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError(f"{label} contains unsupported characters")
    return value


def validate_huggingface_token(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise QwenEndpointOperationError("HF_TOKEN must be a non-empty string")
    if value != value.strip() or not re.fullmatch(r"[\x21-\x7e]+", value):
        raise QwenEndpointOperationError(
            "HF_TOKEN must contain only printable ASCII characters without whitespace"
        )
    return value


def _action_id(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("action_id must be non-empty without surrounding whitespace")
    if len(value) > 240 or any(character in value for character in "\r\n\0"):
        raise ValueError("action_id is invalid")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed Qwen Endpoint lifecycle operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-config")
    commands.add_parser("preflight")
    commands.add_parser("credential-preflight")
    for command in ("create", "start", "status", "wait-ready", "health", "scale-to-zero"):
        item = commands.add_parser(command)
        item.add_argument("--ledger", type=Path, required=True)
        item.add_argument("--evidence", type=Path, required=True)
        item.add_argument("--action-id", required=True)
        item.add_argument("--endpoint-name", required=True)
        item.add_argument("--namespace", required=True)
        if command == "wait-ready":
            item.add_argument("--timeout-seconds", type=float, default=900)
            item.add_argument("--poll-interval-seconds", type=float, default=15)
        if command == "health":
            item.add_argument("--timeout-seconds", type=float, default=30)
        if command in {"start", "wait-ready", "health"}:
            item.add_argument("--phase", choices=("live_gate", "pilot"), default="live_gate")
    verify = commands.add_parser("verify-evidence")
    verify.add_argument("--evidence", type=Path, required=True)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    try:
        if arguments.command in {"verify-config", "preflight"}:
            result = configuration_report(check_sdk=arguments.command == "preflight")
        elif arguments.command == "credential-preflight":
            result = credential_preflight_report()
        elif arguments.command == "verify-evidence":
            value = json.loads(arguments.evidence.read_text(encoding="utf-8"))
            issues = validate_operation_evidence(value)
            if issues:
                raise QwenEndpointOperationError("; ".join(issues))
            result = {
                "valid": str(arguments.evidence.resolve()),
                "evidence_sha256": value["evidence_sha256"],
            }
        else:
            config = json.loads(OPERATIONS_CONFIG_PATH.read_text(encoding="utf-8"))
            token_name = config["management_client"]["token_environment_variable"]
            client = HuggingFaceHubEndpointClient(
                token=os.environ.get(token_name),
                expected_version=config["management_client"]["version"],
            )
            operator = QwenEndpointOperator(
                meter=CombinedPaidStageMeter(arguments.ledger),
                client=client,
                endpoint_name=arguments.endpoint_name,
                namespace=arguments.namespace,
                evidence_path=arguments.evidence,
            )
            if arguments.command == "wait-ready":
                result = operator.wait_ready(
                    action_id=arguments.action_id,
                    timeout_seconds=arguments.timeout_seconds,
                    poll_interval_seconds=arguments.poll_interval_seconds,
                    phase=arguments.phase,
                )
            elif arguments.command == "health":
                result = operator.health(
                    action_id=arguments.action_id,
                    timeout_seconds=arguments.timeout_seconds,
                    phase=arguments.phase,
                )
            elif arguments.command == "start":
                result = operator.start(
                    action_id=arguments.action_id, phase=arguments.phase
                )
            else:
                result = getattr(operator, arguments.command.replace("-", "_"))(
                    action_id=arguments.action_id
                )
    except (OSError, ValueError, json.JSONDecodeError, PaidStageMeterError, QwenEndpointOperationError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
