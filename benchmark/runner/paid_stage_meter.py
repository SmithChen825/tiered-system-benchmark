from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, TypeVar

from .common import REPOSITORY_ROOT
from .openai_paid_stage_authorization import (
    validate_openai_paid_stage_authorization,
)
from .paid_stage_error_policy import (
    POLICY_PATH as DEFAULT_ERROR_POLICY,
    validate_paid_stage_error_policy,
)
from .qwen_paid_stage_authorization import validate_qwen_paid_stage_authorization


SCHEMA_VERSION = "1.0.0"
QWEN = "qwen"
OPENAI = "openai"
PROVIDERS = (QWEN, OPENAI)
DEFAULT_QWEN_AUTHORIZATION = (
    REPOSITORY_ROOT / "benchmark" / "config" / "qwen_paid_stage_authorization.json"
)
DEFAULT_OPENAI_AUTHORIZATION = (
    REPOSITORY_ROOT / "benchmark" / "config" / "openai_paid_stage_authorization.json"
)
_MONEY_QUANTUM = Decimal("0.000000001")
_T = TypeVar("_T")


class PaidStageMeterError(RuntimeError):
    """The paid-stage gate cannot safely authorize another paid action."""


class PaidStageStopped(PaidStageMeterError):
    """The shared meter is stopped and requires explicit operator review."""


class DuplicatePaidAction(PaidStageStopped):
    """An action identifier was reused, so the meter stopped fail-closed."""


@dataclass(frozen=True)
class PaidActionTicket:
    action_id: str
    provider: str
    reserved_usd: Decimal
    sequence: int


def estimate_openai_response_cost_usd(payload: Mapping[str, Any]) -> Decimal:
    """Price a successful GPT-5.4 Standard response from provider usage."""

    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        raise PaidStageMeterError("OpenAI success response omitted usage")
    input_tokens = _nonnegative_integer(usage.get("input_tokens"), "input_tokens")
    output_tokens = _nonnegative_integer(usage.get("output_tokens"), "output_tokens")
    details = usage.get("input_tokens_details")
    cached_tokens = 0
    if details is not None:
        if not isinstance(details, Mapping):
            raise PaidStageMeterError("OpenAI input token details are malformed")
        cached_tokens = _nonnegative_integer(
            details.get("cached_tokens", 0), "cached_tokens"
        )
    if cached_tokens > input_tokens:
        raise PaidStageMeterError("OpenAI cached tokens exceed input tokens")
    uncached_tokens = input_tokens - cached_tokens
    cost = (
        Decimal(uncached_tokens) * Decimal("2.5")
        + Decimal(cached_tokens) * Decimal("0.25")
        + Decimal(output_tokens) * Decimal("15")
    ) / Decimal(1_000_000)
    return _money(cost)


def project_openai_request_cost_usd(payload: Mapping[str, Any]) -> Decimal:
    """Conservative in-flight reserve using UTF-8 bytes and max output tokens."""

    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PaidStageMeterError("OpenAI request is not JSON serializable") from error
    maximum_output = _nonnegative_integer(
        payload.get("max_output_tokens"), "max_output_tokens"
    )
    if maximum_output < 1:
        raise PaidStageMeterError("max_output_tokens must be positive")
    # A token cannot encode fewer than one byte. Treating every request byte as
    # an uncached token is therefore a conservative short-context reservation.
    cost = (
        Decimal(len(encoded)) * Decimal("2.5")
        + Decimal(maximum_output) * Decimal("15")
    ) / Decimal(1_000_000)
    return _money(cost)


class CombinedPaidStageMeter:
    """Persistent fail-closed Qwen/OpenAI paid-stage budget gate."""

    def __init__(
        self,
        ledger_path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(ledger_path).resolve()
        self._lock_path = self.path.with_name(f"{self.path.name}.lock")
        self._now = now or (lambda: datetime.now(timezone.utc))

    @classmethod
    def initialize(
        cls,
        ledger_path: str | Path,
        *,
        qwen_authorization_path: str | Path = DEFAULT_QWEN_AUTHORIZATION,
        openai_authorization_path: str | Path = DEFAULT_OPENAI_AUTHORIZATION,
        error_policy_path: str | Path = DEFAULT_ERROR_POLICY,
        now: Callable[[], datetime] | None = None,
    ) -> CombinedPaidStageMeter:
        meter = cls(ledger_path, now=now)
        qwen = _load_authorization(
            qwen_authorization_path, validate_qwen_paid_stage_authorization, "Qwen"
        )
        openai = _load_authorization(
            openai_authorization_path,
            validate_openai_paid_stage_authorization,
            "OpenAI",
        )
        error_policy = _load_error_policy(error_policy_path)
        if qwen["combined_two_provider_budget"] != openai[
            "combined_two_provider_budget"
        ]:
            raise PaidStageMeterError("Provider authorizations disagree on shared budget")
        if qwen["authorization_boundaries"]["not_before"] != openai[
            "authorization_boundaries"
        ]["not_before"]:
            raise PaidStageMeterError("Provider authorizations disagree on live window")
        combined = qwen["combined_two_provider_budget"]
        if error_policy["authorized_budget_id"] != combined["authorization_id"]:
            raise PaidStageMeterError("Error policy is bound to another budget")
        created = meter._timestamp()
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "authorization_id": combined["authorization_id"],
            "authorization_sha256": {
                QWEN: qwen["authorization_sha256"],
                OPENAI: openai["authorization_sha256"],
            },
            "paid_stage_error_policy": {
                "policy_id": error_policy["policy_id"],
                "policy_sha256": error_policy["policy_sha256"],
                "raw_sha256": hashlib.sha256(
                    Path(error_policy_path).read_bytes()
                ).hexdigest(),
            },
            "currency": "USD",
            "status": "ACTIVE",
            "stop_reason": None,
            "not_before": qwen["authorization_boundaries"]["not_before"],
            "created_at": created,
            "updated_at": created,
            "sequence": 0,
            "limits_usd": {
                "combined_operational_stop": _money_text(
                    combined["operational_stop_threshold_usd"]
                ),
                QWEN: _money_text(combined["qwen_operational_stop_usd"]),
                OPENAI: _money_text(combined["openai_operational_stop_usd"]),
            },
            "hard_limits_usd": {
                "combined": _money_text(combined["hard_budget_usd"]),
                QWEN: _money_text(combined["qwen_hard_allocation_usd"]),
                OPENAI: _money_text(combined["openai_hard_allocation_usd"]),
            },
            "local_increment_estimate_usd": {QWEN: "0", OPENAI: "0"},
            "account_visible_spend_usd": {QWEN: "0", OPENAI: "0"},
            "pending_actions": {},
            "seen_action_ids": [],
            "events": [],
            "finalization": None,
            "qwen_runtime": {
                "active": False,
                "started_at": None,
                "completed_seconds": "0",
                "hourly_rate_usd": _money_text(
                    qwen["cost_controls"]["public_reference_hourly_rate_usd"]
                ),
                "maximum_seconds": str(
                    qwen["time_controls"][
                        "maximum_cumulative_endpoint_running_seconds"
                    ]
                ),
            },
        }
        meter.path.parent.mkdir(parents=True, exist_ok=True)
        with meter._exclusive_lock():
            if meter.path.exists():
                raise PaidStageMeterError("Paid-stage ledger already exists")
            meter._write(state)
        return meter

    @classmethod
    def initialize_successor(
        cls,
        ledger_path: str | Path,
        *,
        predecessor_ledger_path: str | Path,
        successor_id: str,
        qwen_authorization_path: str | Path = DEFAULT_QWEN_AUTHORIZATION,
        openai_authorization_path: str | Path = DEFAULT_OPENAI_AUTHORIZATION,
        error_policy_path: str | Path = DEFAULT_ERROR_POLICY,
        now: Callable[[], datetime] | None = None,
    ) -> CombinedPaidStageMeter:
        predecessor_path = Path(predecessor_ledger_path).resolve()
        predecessor = cls(predecessor_path, now=now).snapshot()
        predecessor_status = predecessor["status"]
        prior_status = predecessor_status
        if predecessor_status == "FINALIZED":
            finalization = predecessor.get("finalization")
            prior_status = (
                finalization.get("prior_status")
                if isinstance(finalization, Mapping)
                else None
            )
        if prior_status not in {"ACTIVE", "STOPPED"} or (
            prior_status == "ACTIVE" and predecessor_status != "FINALIZED"
        ):
            raise PaidStageMeterError(
                "Successor requires a stopped or explicitly finalized predecessor ledger"
            )
        if predecessor["pending_actions"] or predecessor["qwen_runtime"]["active"]:
            raise PaidStageMeterError(
                "Successor requires no pending actions and an inactive Qwen runtime"
            )
        successor_id = _action_id(successor_id)
        successor_qwen_authorization = _load_authorization(
            qwen_authorization_path,
            validate_qwen_paid_stage_authorization,
            "Qwen",
        )
        successor_budget = successor_qwen_authorization[
            "combined_two_provider_budget"
        ]
        meter = cls.initialize(
            ledger_path,
            qwen_authorization_path=qwen_authorization_path,
            openai_authorization_path=openai_authorization_path,
            error_policy_path=error_policy_path,
            now=now,
        )
        with meter._exclusive_lock():
            state = meter._read()
            if (
                state["authorization_id"] != predecessor["authorization_id"]
                and successor_budget.get("supersedes_authorization_id")
                != predecessor["authorization_id"]
            ):
                raise PaidStageMeterError(
                    "Successor authorization does not supersede predecessor authorization"
                )
            state["local_increment_estimate_usd"] = dict(
                predecessor["local_increment_estimate_usd"]
            )
            state["account_visible_spend_usd"] = dict(
                predecessor["account_visible_spend_usd"]
            )
            state["seen_action_ids"].append(successor_id)
            meter._event(
                state,
                "successor_ledger_initialized",
                successor_id,
                "combined",
                details={
                    "predecessor_ledger": str(predecessor_path),
                    "predecessor_raw_sha256": hashlib.sha256(
                        predecessor_path.read_bytes()
                    ).hexdigest(),
                    "predecessor_state_sha256": predecessor["state_sha256"],
                    "predecessor_stop_reason": predecessor["stop_reason"],
                    "carried_local_increment_estimate_usd": state[
                        "local_increment_estimate_usd"
                    ],
                    "carried_account_visible_spend_usd": state[
                        "account_visible_spend_usd"
                    ],
                },
            )
            meter._apply_threshold_stop(state)
            if state["status"] != "ACTIVE":
                raise PaidStageStopped(
                    "Carried-forward spend leaves no authorized successor budget"
                )
            meter._write(state)
        return meter

    def snapshot(self) -> dict[str, Any]:
        with self._exclusive_lock():
            state = self._read()
            before = _state_sha256(state)
            self._refresh_qwen_runtime(state)
            self._apply_threshold_stop(state)
            if _state_sha256(state) != before:
                self._write(state)
            return json.loads(json.dumps(state))

    def reserve_action(
        self,
        action_id: str,
        provider: str,
        projected_increment_usd: Decimal | float | str,
        *,
        require_qwen_runtime: bool = False,
    ) -> PaidActionTicket:
        provider = _provider(provider)
        action_id = _action_id(action_id)
        projected = _money(projected_increment_usd)
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state)
            self._ensure_active(state)
            if action_id in state["seen_action_ids"]:
                self._stop(state, f"duplicate_action_id:{action_id}")
                self._write(state)
                raise DuplicatePaidAction(f"Duplicate paid action blocked: {action_id}")
            if state["pending_actions"]:
                self._stop(state, "concurrent_paid_action_prohibited")
                self._write(state)
                raise PaidStageStopped("Another paid action is still pending")
            if require_qwen_runtime and not state["qwen_runtime"]["active"]:
                self._stop(state, "qwen_runtime_not_active")
                self._write(state)
                raise PaidStageStopped("Qwen HTTP action requires active runtime meter")
            self._guard_projection(state, provider, projected)
            state["seen_action_ids"].append(action_id)
            self._event(state, "action_reserved", action_id, provider)
            state["pending_actions"][action_id] = {
                "provider": provider,
                "reserved_usd": _money_text(projected),
                "sequence": state["sequence"],
                "reserved_at": self._timestamp(),
            }
            self._write(state)
            return PaidActionTicket(action_id, provider, projected, state["sequence"])

    def settle_action(
        self,
        ticket: PaidActionTicket,
        *,
        outcome: str,
        actual_increment_usd: Decimal | float | str | None,
        stop_stage_on_failure: bool = True,
    ) -> None:
        if outcome not in {
            "success",
            "interface_failure",
            "provider_failure",
            "retryable_request_failure",
            "retryable_provider_failure",
        }:
            raise ValueError("Unsupported paid action outcome")
        if outcome == "success" and stop_stage_on_failure:
            stop_stage_on_failure = False
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state)
            pending = state["pending_actions"].get(ticket.action_id)
            if not isinstance(pending, dict) or (
                pending.get("provider") != ticket.provider
                or pending.get("sequence") != ticket.sequence
                or _money(pending.get("reserved_usd")) != ticket.reserved_usd
            ):
                self._stop(state, f"ticket_mismatch:{ticket.action_id}")
                self._write(state)
                raise PaidStageStopped("Paid action ticket does not match ledger")
            if actual_increment_usd is None:
                actual = ticket.reserved_usd
            else:
                actual = _money(actual_increment_usd)
            local = _money(
                state["local_increment_estimate_usd"][ticket.provider]
            ) + actual
            state["local_increment_estimate_usd"][ticket.provider] = _money_text(local)
            del state["pending_actions"][ticket.action_id]
            self._event(state, f"action_{outcome}", ticket.action_id, ticket.provider)
            if outcome != "success" and stop_stage_on_failure:
                self._stop(state, f"{outcome}:{ticket.action_id}")
            self._apply_threshold_stop(state)
            self._write(state)

    def execute(
        self,
        *,
        action_id: str,
        provider: str,
        projected_increment_usd: Decimal | float | str,
        operation: Callable[[], _T],
        actual_increment: Callable[[_T], Decimal | float | str],
        response_succeeded: Callable[[_T], bool] | None = None,
        require_qwen_runtime: bool = False,
        operation_failure_stops_stage: bool
        | Callable[[BaseException], bool] = True,
        response_failure_stops_stage: bool | Callable[[_T], bool] = True,
    ) -> _T:
        ticket = self.reserve_action(
            action_id,
            provider,
            projected_increment_usd,
            require_qwen_runtime=require_qwen_runtime,
        )
        try:
            result = operation()
        except BaseException as error:
            stop_stage = (
                operation_failure_stops_stage(error)
                if callable(operation_failure_stops_stage)
                else operation_failure_stops_stage
            )
            self.settle_action(
                ticket,
                outcome=(
                    "interface_failure" if stop_stage else "retryable_request_failure"
                ),
                actual_increment_usd=None,
                stop_stage_on_failure=stop_stage,
            )
            if stop_stage:
                raise PaidStageStopped(
                    f"Interface failure stopped paid action: {action_id}"
                ) from error
            raise
        try:
            actual = actual_increment(result)
            succeeded = True if response_succeeded is None else response_succeeded(result)
        except BaseException:
            self.settle_action(
                ticket, outcome="interface_failure", actual_increment_usd=None
            )
            raise
        stop_stage = False
        if not succeeded:
            stop_stage = (
                response_failure_stops_stage(result)
                if callable(response_failure_stops_stage)
                else response_failure_stops_stage
            )
        self.settle_action(
            ticket,
            outcome=(
                "success"
                if succeeded
                else (
                    "provider_failure"
                    if stop_stage
                    else "retryable_provider_failure"
                )
            ),
            actual_increment_usd=actual,
            stop_stage_on_failure=stop_stage,
        )
        if not succeeded and stop_stage:
            raise PaidStageStopped(f"Provider failure stopped paid action: {action_id}")
        return result

    def observe_provider_spend(
        self,
        *,
        observation_id: str,
        provider: str,
        cumulative_spend_usd: Decimal | float | str,
        evidence_reference: str | None = None,
        evidence_sha256: str | None = None,
    ) -> None:
        provider = _provider(provider)
        observation_id = _action_id(observation_id)
        observed = _money(cumulative_spend_usd)
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state)
            if state["status"] == "FINALIZED":
                raise PaidStageStopped("Finalized paid-stage ledger is immutable")
            if observation_id in state["seen_action_ids"]:
                self._stop(state, f"duplicate_action_id:{observation_id}")
                self._write(state)
                raise DuplicatePaidAction(
                    f"Duplicate spend observation blocked: {observation_id}"
                )
            previous = _money(state["account_visible_spend_usd"][provider])
            if observed < previous:
                self._stop(state, f"non_monotonic_provider_spend:{provider}")
                self._write(state)
                raise PaidStageStopped("Provider spend observation moved backwards")
            state["seen_action_ids"].append(observation_id)
            state["account_visible_spend_usd"][provider] = _money_text(observed)
            details: dict[str, Any] = {
                "cumulative_spend_usd": _money_text(observed)
            }
            if evidence_reference is not None or evidence_sha256 is not None:
                details["evidence_reference"] = _evidence_reference(
                    evidence_reference
                )
                details["evidence_sha256"] = _sha256(evidence_sha256)
            self._event(
                state,
                "provider_spend_observed",
                observation_id,
                provider,
                details=details,
            )
            self._apply_threshold_stop(state)
            self._write(state)

    def finalize_stage(self, evidence_id: str) -> dict[str, Any]:
        evidence_id = _action_id(evidence_id)
        with self._exclusive_lock():
            state = self._read()
            existing = state["finalization"]
            if state["status"] == "FINALIZED":
                if isinstance(existing, dict) and existing.get("evidence_id") == evidence_id:
                    return json.loads(json.dumps(state))
                raise PaidStageStopped("Ledger was finalized for different evidence")
            self._refresh_qwen_runtime(state)
            if state["qwen_runtime"]["active"]:
                raise PaidStageMeterError(
                    "Qwen runtime must be positively stopped before finalization"
                )
            if state["pending_actions"]:
                raise PaidStageMeterError(
                    "Pending paid actions must be settled before finalization"
                )
            latest_observations: dict[str, Mapping[str, Any]] = {}
            for event in state["events"]:
                if event["event"] == "provider_spend_observed":
                    latest_observations[event["provider"]] = event
            if set(latest_observations) != set(PROVIDERS) or any(
                not isinstance(latest_observations[provider].get("details"), dict)
                or not latest_observations[provider]["details"].get("evidence_sha256")
                for provider in PROVIDERS
            ):
                raise PaidStageMeterError(
                    "Final account-visible evidence is required for both providers"
                )
            prior_status = state["status"]
            state["status"] = "FINALIZED"
            state["finalization"] = {
                "evidence_id": evidence_id,
                "prior_status": prior_status,
                "finalized_at": self._timestamp(),
            }
            self._event(state, "stage_finalized", evidence_id, "combined")
            self._write(state)
            return json.loads(json.dumps(state))

    def start_qwen_runtime(self, action_id: str, *, hourly_rate_usd: Any) -> None:
        action_id = _action_id(action_id)
        rate = _money(hourly_rate_usd)
        if rate <= 0:
            raise ValueError("Qwen hourly rate must be positive")
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state)
            self._ensure_active(state)
            if action_id in state["seen_action_ids"]:
                self._stop(state, f"duplicate_action_id:{action_id}")
                self._write(state)
                raise DuplicatePaidAction(f"Duplicate paid action blocked: {action_id}")
            runtime = state["qwen_runtime"]
            if runtime["active"]:
                self._stop(state, "qwen_runtime_already_active")
                self._write(state)
                raise PaidStageStopped("Qwen runtime is already active")
            if (
                Decimal(runtime["completed_seconds"]) > 0
                and _money(runtime["hourly_rate_usd"]) != rate
            ):
                self._stop(state, "qwen_hourly_rate_changed")
                self._write(state)
                raise PaidStageStopped(
                    "Qwen hourly rate changed; reauthorization is required"
                )
            one_minute = _money(rate / Decimal(60))
            self._guard_projection(state, QWEN, one_minute)
            state["seen_action_ids"].append(action_id)
            runtime["active"] = True
            runtime["started_at"] = self._timestamp()
            runtime["hourly_rate_usd"] = _money_text(rate)
            self._event(state, "qwen_runtime_started", action_id, QWEN)
            self._write(state)

    def stop_qwen_runtime(self, action_id: str) -> None:
        action_id = _action_id(action_id)
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state, stop=True)
            if action_id in state["seen_action_ids"]:
                self._stop(state, f"duplicate_action_id:{action_id}")
                self._write(state)
                raise DuplicatePaidAction(f"Duplicate paid action blocked: {action_id}")
            state["seen_action_ids"].append(action_id)
            self._event(state, "qwen_runtime_stopped", action_id, QWEN)
            self._apply_threshold_stop(state)
            self._write(state)

    def execute_qwen_runtime_start(
        self,
        *,
        action_id: str,
        hourly_rate_usd: Any,
        operation: Callable[[], _T],
    ) -> _T:
        """Start metering before an Endpoint start/create management call."""

        self.start_qwen_runtime(action_id, hourly_rate_usd=hourly_rate_usd)
        try:
            return operation()
        except BaseException:
            self.record_interface_failure(f"{action_id}:interface_failure", QWEN)
            # Runtime metering intentionally remains active because an ambiguous
            # management failure does not prove the Endpoint is scaled to zero.
            raise

    def execute_qwen_runtime_stop(
        self, *, action_id: str, operation: Callable[[], _T]
    ) -> _T:
        """Stop metering only after scale-to-zero is positively confirmed."""

        try:
            result = operation()
        except BaseException:
            self.record_interface_failure(f"{action_id}:interface_failure", QWEN)
            raise
        self.stop_qwen_runtime(action_id)
        return result

    def record_interface_failure(self, action_id: str, provider: str) -> None:
        provider = _provider(provider)
        action_id = _action_id(action_id)
        with self._exclusive_lock():
            state = self._read()
            self._refresh_qwen_runtime(state)
            if action_id in state["seen_action_ids"]:
                self._stop(state, f"duplicate_action_id:{action_id}")
            else:
                state["seen_action_ids"].append(action_id)
                self._event(state, "interface_failure", action_id, provider)
                self._stop(state, f"interface_failure:{action_id}")
            self._write(state)

    def _refresh_qwen_runtime(self, state: dict[str, Any], *, stop: bool = False) -> None:
        runtime = state["qwen_runtime"]
        if not runtime["active"]:
            if stop:
                self._stop(state, "qwen_runtime_not_active")
                raise PaidStageStopped("Qwen runtime is not active")
            return
        started = _parse_timestamp(runtime["started_at"])
        current = self._current_time()
        elapsed = Decimal(str((current - started).total_seconds()))
        if elapsed < 0:
            self._stop(state, "clock_moved_backwards")
            raise PaidStageStopped("Clock moved backwards during Qwen runtime")
        prior_seconds = Decimal(runtime["completed_seconds"])
        total_seconds = prior_seconds + elapsed
        billed_minutes = (total_seconds / Decimal(60)).to_integral_value(
            rounding=ROUND_CEILING
        )
        rate = _money(runtime["hourly_rate_usd"])
        state["local_increment_estimate_usd"][QWEN] = _money_text(
            billed_minutes * rate / Decimal(60)
        )
        if total_seconds >= Decimal(runtime["maximum_seconds"]):
            self._stop(state, "qwen_runtime_time_limit_reached")
        if stop:
            runtime["completed_seconds"] = str(total_seconds)
            runtime["started_at"] = None
            runtime["active"] = False

    def _guard_projection(
        self, state: dict[str, Any], provider: str, projected: Decimal
    ) -> None:
        effective = self._effective_spend(state)
        provider_limit = _money(state["limits_usd"][provider])
        combined_limit = _money(state["limits_usd"]["combined_operational_stop"])
        if effective[provider] >= provider_limit:
            self._stop(state, f"{provider}_operational_stop_reached")
            self._write(state)
            raise PaidStageStopped(f"{provider} operational stop reached")
        if sum(effective.values(), Decimal(0)) >= combined_limit:
            self._stop(state, "combined_operational_stop_reached")
            self._write(state)
            raise PaidStageStopped("Combined operational stop reached")
        if effective[provider] + projected > provider_limit:
            self._stop(state, f"{provider}_projection_exceeds_stop")
            self._write(state)
            raise PaidStageStopped(f"Projected {provider} spend exceeds its stop")
        if sum(effective.values(), Decimal(0)) + projected > combined_limit:
            self._stop(state, "combined_projection_exceeds_stop")
            self._write(state)
            raise PaidStageStopped("Projected combined spend exceeds its stop")

    def _apply_threshold_stop(self, state: dict[str, Any]) -> None:
        effective = self._effective_spend(state)
        for provider in PROVIDERS:
            if effective[provider] >= _money(state["limits_usd"][provider]):
                self._stop(state, f"{provider}_operational_stop_reached")
                return
        if sum(effective.values(), Decimal(0)) >= _money(
            state["limits_usd"]["combined_operational_stop"]
        ):
            self._stop(state, "combined_operational_stop_reached")

    def _effective_spend(self, state: Mapping[str, Any]) -> dict[str, Decimal]:
        pending = {provider: Decimal(0) for provider in PROVIDERS}
        for item in state["pending_actions"].values():
            pending[item["provider"]] += _money(item["reserved_usd"])
        return {
            provider: max(
                _money(state["local_increment_estimate_usd"][provider]),
                _money(state["account_visible_spend_usd"][provider]),
            )
            + pending[provider]
            for provider in PROVIDERS
        }

    def _ensure_active(self, state: Mapping[str, Any]) -> None:
        if state["status"] != "ACTIVE":
            raise PaidStageStopped(
                f"Paid-stage meter is stopped: {state.get('stop_reason')}"
            )
        if self._current_time() < _parse_timestamp(state["not_before"]):
            mutable = state if isinstance(state, dict) else dict(state)
            self._stop(mutable, "paid_action_before_authorized_window")
            if mutable is not state:
                raise PaidStageStopped("Paid action is earlier than the authorized window")
            self._write(mutable)
            raise PaidStageStopped("Paid action is earlier than the authorized window")

    def _stop(self, state: dict[str, Any], reason: str) -> None:
        if state["status"] == "ACTIVE":
            state["status"] = "STOPPED"
            state["stop_reason"] = reason

    def _event(
        self,
        state: dict[str, Any],
        event: str,
        action_id: str,
        provider: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        state["sequence"] += 1
        item = {
            "sequence": state["sequence"],
            "event": event,
            "action_id": action_id,
            "provider": provider,
            "at": self._timestamp(),
        }
        if details is not None:
            item["details"] = dict(details)
        state["events"].append(item)

    def _timestamp(self) -> str:
        return self._current_time().isoformat().replace("+00:00", "Z")

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise PaidStageMeterError("Meter clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            raise PaidStageMeterError("Paid-stage ledger is locked; call blocked") from error
        try:
            os.close(descriptor)
            yield
        finally:
            try:
                self._lock_path.unlink()
            except FileNotFoundError:
                pass

    def _read(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            state = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PaidStageMeterError("Paid-stage ledger cannot be read safely") from error
        if not isinstance(state, dict):
            raise PaidStageMeterError("Paid-stage ledger root must be an object")
        integrity = state.get("state_sha256")
        expected = _state_sha256(state)
        if not isinstance(integrity, str) or integrity != expected:
            raise PaidStageMeterError("Paid-stage ledger integrity check failed")
        required = {
            "schema_version",
            "authorization_id",
            "authorization_sha256",
            "paid_stage_error_policy",
            "currency",
            "status",
            "stop_reason",
            "not_before",
            "created_at",
            "updated_at",
            "sequence",
            "limits_usd",
            "hard_limits_usd",
            "local_increment_estimate_usd",
            "account_visible_spend_usd",
            "pending_actions",
            "seen_action_ids",
            "events",
            "finalization",
            "qwen_runtime",
            "state_sha256",
        }
        if set(state) != required or state["schema_version"] != SCHEMA_VERSION:
            raise PaidStageMeterError("Paid-stage ledger schema mismatch")
        return state

    def _write(self, state: dict[str, Any]) -> None:
        state["updated_at"] = self._timestamp()
        state["state_sha256"] = _state_sha256(state)
        encoded = (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def _load_authorization(
    path: str | Path,
    validator: Callable[[dict[str, Any]], list[str]],
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PaidStageMeterError(f"{label} authorization cannot be read") from error
    if not isinstance(value, dict):
        raise PaidStageMeterError(f"{label} authorization must be an object")
    issues = validator(value)
    if issues:
        raise PaidStageMeterError(f"{label} authorization invalid: {'; '.join(issues)}")
    return value


def _load_error_policy(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PaidStageMeterError("Paid-stage error policy cannot be read") from error
    if not isinstance(value, dict):
        raise PaidStageMeterError("Paid-stage error policy must be an object")
    issues = validate_paid_stage_error_policy(value)
    if issues:
        raise PaidStageMeterError(
            f"Paid-stage error policy invalid: {'; '.join(issues)}"
        )
    return value


def _state_sha256(state: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in state.items() if key != "state_sha256"}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider(value: str) -> str:
    if value not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}")
    return value


def _action_id(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("action_id must be non-empty without surrounding whitespace")
    if len(value) > 240 or any(character in value for character in "\r\n\0"):
        raise ValueError("action_id is invalid")
    return value


def _evidence_reference(value: str | None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("evidence_reference must be non-empty")
    if len(value) > 240 or any(character in value for character in "\r\n\0"):
        raise ValueError("evidence_reference is invalid")
    return value


def _sha256(value: str | None) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("evidence_sha256 must be a lowercase SHA-256")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("evidence_sha256 must be a lowercase SHA-256")
    return value


def _money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Money value must be a nonnegative finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("Money value must be a nonnegative finite decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError("Money value must be a nonnegative finite decimal")
    return result.quantize(_MONEY_QUANTUM)


def _money_text(value: Any) -> str:
    result = _money(value)
    return format(result.normalize(), "f") if result else "0"


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PaidStageMeterError(f"{label} must be a nonnegative integer")
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PaidStageMeterError("Meter timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PaidStageMeterError("Meter timestamp is malformed") from error
    if parsed.tzinfo is None:
        raise PaidStageMeterError("Meter timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)
