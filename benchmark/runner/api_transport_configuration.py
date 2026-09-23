from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT  # type: ignore


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
EXPECTED_IMPLEMENTATION_PATHS = [
    "benchmark/runner/paid_stage_meter.py",
    "benchmark/runner/paid_stage_operations.py",
    "benchmark/runner/openai_live_smoke.py",
    "benchmark/runner/qwen_live_smoke.py",
    "benchmark/runner/qwen_endpoint_operations.py",
    "benchmark/runner/api_pilot_run.py",
    "benchmark/runner/api_wrapper/transports/live_http.py",
    "benchmark/runner/api_wrapper/transports/openai_responses.py",
    "benchmark/runner/api_wrapper/transports/qwen_vllm.py",
]
MAIN_IMPLEMENTATION_PATHS = [
    "benchmark/runner/paid_stage_meter.py",
    "benchmark/runner/paid_stage_operations.py",
    "benchmark/runner/openai_paid_stage_authorization.py",
    "benchmark/runner/qwen_paid_stage_authorization.py",
    "benchmark/runner/paid_stage_error_policy.py",
    "benchmark/runner/qwen_endpoint_operations.py",
    "benchmark/runner/qwen_main_endpoint_operations.py",
    "benchmark/runner/api_pilot_run.py",
    "benchmark/runner/api_main_run.py",
    "benchmark/runner/api_wrapper/transports/live_http.py",
    "benchmark/runner/api_wrapper/transports/openai_responses.py",
    "benchmark/runner/api_wrapper/transports/qwen_vllm.py",
]
OPENAI_PENDING = "openai_account_visible_pricing_and_live_smoke"
QWEN_PENDING = "qwen_frozen_live_deployment_and_smoke"
EXPECTED_PYTHON_RUNTIME_VERSION = "3.12.13"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_path_hash(
    value: Any,
    *,
    repository_root: Path,
    label: str,
    allow_null: bool = False,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        return [f"{label} must contain path and sha256"]
    raw_path = value["path"]
    digest = value["sha256"]
    if allow_null and raw_path is None and digest is None:
        return []
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        return [f"{label}.path must be a repository-relative POSIX path"]
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return [f"{label}.path must stay within the repository"]
    path = (repository_root / relative).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        return [f"{label}.path must stay within the repository"]
    if not path.is_file():
        issues.append(f"{label}.path does not exist")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append(f"{label}.sha256 must be a lowercase SHA-256")
    elif path.is_file() and file_sha256(path) != digest:
        issues.append(f"{label}.sha256 mismatch")
    return issues


def _validate_live_gate_evidence(
    value: Any,
    *,
    repository_root: Path,
    label: str,
) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"smoke", "account_observation"}:
        return [f"{label} must contain smoke and account_observation"]
    issues: list[str] = []
    for name in ("smoke", "account_observation"):
        issues.extend(
            _validate_path_hash(
                value[name],
                repository_root=repository_root,
                label=f"{label}.{name}",
            )
        )
    return issues


def validate_api_transport_configuration(
    value: dict[str, Any],
    *,
    require_frozen: bool = False,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    issues: list[str] = []
    expected_fields = {
        "schema_version",
        "status",
        "freeze_scope",
        "configuration_id",
        "transport_contract",
        "paid_stage_error_policy",
        "implementation_files",
        "common_runtime",
        "openai",
        "qwen",
        "pending_decisions",
        "notes",
    }
    if set(value) != expected_fields:
        return ["API transport configuration fields do not match the contract"]
    if value["schema_version"] != "1.1.0":
        issues.append("schema_version must be 1.1.0")
    status = value["status"]
    scope = value["freeze_scope"]
    if status not in {"CANDIDATE", "FROZEN"}:
        issues.append("status must be CANDIDATE or FROZEN")
    if status == "CANDIDATE" and scope is not None:
        issues.append("candidate freeze_scope must be null")
    if status == "FROZEN" and scope not in {"pilot_candidate", "main_experiment"}:
        issues.append("frozen freeze_scope must be pilot_candidate or main_experiment")
    if require_frozen and status != "FROZEN":
        issues.append("API transport configuration must be FROZEN for execution")
    expected_configuration_id = (
        "tsb-api-transport-main-v2"
        if scope == "main_experiment"
        else "tsb-api-transport-pilot-v1"
    )
    if value["configuration_id"] != expected_configuration_id:
        issues.append("configuration_id mismatch")
    issues.extend(
        _validate_path_hash(
            value["transport_contract"],
            repository_root=repository_root,
            label="transport_contract",
        )
    )
    issues.extend(
        _validate_path_hash(
            value["paid_stage_error_policy"],
            repository_root=repository_root,
            label="paid_stage_error_policy",
        )
    )
    expected_error_policy_path = (
        "benchmark/config/paid_main_error_policy_20260923_l3_02_r03_openai.json"
        if scope == "main_experiment"
        else "benchmark/config/paid_stage_error_policy.json"
    )
    if value["paid_stage_error_policy"].get("path") != expected_error_policy_path:
        issues.append("paid_stage_error_policy.path mismatch")
    else:
        try:
            from .paid_stage_error_policy import validate_paid_stage_error_policy

            error_policy = json.loads(
                (repository_root / expected_error_policy_path).read_text(
                    encoding="utf-8"
                )
            )
            issues.extend(
                "paid_stage_error_policy: " + issue
                for issue in validate_paid_stage_error_policy(error_policy)
            )
        except (ImportError, OSError, UnicodeError, json.JSONDecodeError) as error:
            issues.append(f"paid_stage_error_policy could not be validated: {error}")
    implementations = value["implementation_files"]
    expected_implementation_paths = (
        MAIN_IMPLEMENTATION_PATHS if scope == "main_experiment" else EXPECTED_IMPLEMENTATION_PATHS
    )
    if not isinstance(implementations, list) or [
        item.get("path") for item in implementations if isinstance(item, dict)
    ] != expected_implementation_paths:
        issues.append("implementation_files must contain the exact frozen transport paths")
    else:
        for index, item in enumerate(implementations):
            issues.extend(
                _validate_path_hash(
                    item,
                    repository_root=repository_root,
                    label=f"implementation_files[{index}]",
                )
            )
    runtime = value["common_runtime"]
    if not isinstance(runtime, dict) or set(runtime) != {
        "http_client",
        "sdk_implicit_retries",
        "tls_certificate_verification",
        "live_authorization_environment_variable",
        "live_authorization_exact_value",
        "paid_stage_meter_path_environment_variable",
        "paid_stage_phase_constructor_argument_required",
        "python_runtime_version",
    }:
        issues.append("common_runtime structure mismatch")
    else:
        fixed_runtime = dict(runtime)
        python_version = fixed_runtime.pop("python_runtime_version")
        if fixed_runtime != {
            "http_client": "python_standard_library_urllib",
            "sdk_implicit_retries": 0,
            "tls_certificate_verification": True,
            "live_authorization_environment_variable": "TSB_LIVE_PROVIDER_AUTHORIZATION",
            "live_authorization_exact_value": "I_AUTHORIZE_PAID_PROVIDER_CALLS",
            "paid_stage_meter_path_environment_variable": "TSB_PAID_STAGE_METER_PATH",
            "paid_stage_phase_constructor_argument_required": True,
        }:
            issues.append("common_runtime fixed controls mismatch")
        if python_version != EXPECTED_PYTHON_RUNTIME_VERSION:
            issues.append(
                f"python_runtime_version must equal {EXPECTED_PYTHON_RUNTIME_VERSION}"
            )
    openai = value["openai"]
    expected_openai_fields = {
        "endpoint",
        "model_snapshot",
        "api_key_environment_variable",
        "requester_class",
        "paid_stage_authorization",
        "live_smoke_status",
        "account_visible_pricing_basis",
        "live_gate_evidence",
    }
    if scope == "main_experiment":
        expected_openai_fields.add("replacement_run_authorizations")
    if not isinstance(openai, dict) or set(openai) != expected_openai_fields:
        issues.append("openai structure mismatch")
    else:
        if {
            "endpoint": openai["endpoint"],
            "model_snapshot": openai["model_snapshot"],
            "api_key_environment_variable": openai["api_key_environment_variable"],
            "requester_class": openai["requester_class"],
        } != {
            "endpoint": "https://api.openai.com/v1/responses",
            "model_snapshot": "gpt-5.4-2026-03-05",
            "api_key_environment_variable": "TSB_OPENAI_API_KEY",
            "requester_class": "OpenAIResponsesHttpRequester",
        }:
            issues.append("openai fixed configuration mismatch")
        issues.extend(
            _validate_path_hash(
                openai["paid_stage_authorization"],
                repository_root=repository_root,
                label="openai.paid_stage_authorization",
            )
        )
        expected_openai_authorization_path = (
            "benchmark/config/openai_paid_main_authorization_20260923_l3_02_r03.json"
            if scope == "main_experiment"
            else "benchmark/config/openai_paid_stage_authorization.json"
        )
        if openai["paid_stage_authorization"].get("path") != expected_openai_authorization_path:
            issues.append(
                "openai.paid_stage_authorization.path must name the independent OpenAI authorization"
            )
        else:
            try:
                from .openai_paid_stage_authorization import (
                    validate_openai_paid_stage_authorization,
                )

                authorization = json.loads(
                    (repository_root / expected_openai_authorization_path).read_text(
                        encoding="utf-8"
                    )
                )
                issues.extend(
                    "openai.paid_stage_authorization: " + issue
                    for issue in validate_openai_paid_stage_authorization(authorization)
                )
            except (ImportError, OSError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(
                    f"openai.paid_stage_authorization could not be validated: {error}"
                )
        if scope == "main_experiment":
            replacement_path = (
                "benchmark/config/openai_main_l1_replacement_authorization_20260901_a02.json"
            )
            replacements = openai["replacement_run_authorizations"]
            if not isinstance(replacements, list) or len(replacements) != 5:
                issues.append(
                    "openai.replacement_run_authorizations must contain five authorized replacements"
                )
            else:
                replacement_paths = [
                    replacement_path,
                    "benchmark/config/openai_main_l1_replacement_authorization_20260901_a03.json",
                    "benchmark/config/openai_main_l1_r02_replacement_authorization_20260908_a02.json",
                    "benchmark/config/openai_main_l1_r02_replacement_authorization_20260908_a03.json",
                    "benchmark/config/openai_main_l1_03_r02_replacement_authorization_20260914_a02.json",
                ]
                for index, reference in enumerate(replacements):
                    issues.extend(
                        _validate_path_hash(
                            reference,
                            repository_root=repository_root,
                            label=f"openai.replacement_run_authorizations[{index}]",
                        )
                    )
                if [item.get("path") for item in replacements] != replacement_paths:
                    issues.append("OpenAI main replacement authorization paths mismatch")
                else:
                    try:
                        loaded = [
                            json.loads((repository_root / path).read_text(encoding="utf-8"))
                            for path in replacement_paths
                        ]
                        expected_ids = [
                            "main-L1-01-gpt-5-4-r01-a02",
                            "main-L1-01-gpt-5-4-r01-a03",
                            "main-L1-01-gpt-5-4-r02-a02",
                            "main-L1-01-gpt-5-4-r02-a03",
                            "main-L1-03-gpt-5-4-r02-a02",
                        ]
                        expected_values = [
                            ("main-L1-01-gpt-5-4-r01-a01", 2, 1, 1),
                            ("main-L1-01-gpt-5-4-r01-a01", 3, 1, 1),
                            ("main-L1-01-gpt-5-4-r02-a01", 2, 2, 3),
                            ("main-L1-01-gpt-5-4-r02-a01", 3, 2, 3),
                            ("main-L1-03-gpt-5-4-r02-a01", 2, 2, 4),
                        ]
                        for index, (replacement, run_id, values) in enumerate(
                            zip(loaded, expected_ids, expected_values, strict=True)
                        ):
                            base_run_id, expected_attempt, repetition, order_position = values
                            for field, wanted in {
                                "base_schedule_run_id": base_run_id,
                                "replacement_run_id": run_id,
                                "replacement_attempt": expected_attempt,
                                "task_id": "L1-03" if index == 4 else "L1-01",
                                "system_id": "gpt-5.4",
                                "repetition": repetition,
                                "order_position": order_position,
                                "original_run_validity_and_outcome_unchanged": True,
                                "provider_execution_authorized_by_this_record_alone": False,
                            }.items():
                                if replacement.get(field) != wanted:
                                    issues.append(
                                        f"openai.replacement_run_authorizations[{index}].{field} mismatch"
                                    )
                    except (OSError, UnicodeError, json.JSONDecodeError) as error:
                        issues.append(
                            f"OpenAI main replacement authorization could not be validated: {error}"
                        )
        openai_status = openai["live_smoke_status"]
        if openai_status == "PENDING":
            if status == "FROZEN":
                issues.append("frozen OpenAI live smoke and pricing evidence are required")
            if (
                openai["account_visible_pricing_basis"] is not None
                or openai["live_gate_evidence"] is not None
            ):
                issues.append("pending OpenAI live evidence must remain null")
        elif openai_status == "PASSED":
            issues.extend(
                _validate_path_hash(
                    openai["account_visible_pricing_basis"],
                    repository_root=repository_root,
                    label="openai.account_visible_pricing_basis",
                )
            )
            issues.extend(
                _validate_live_gate_evidence(
                    openai["live_gate_evidence"],
                    repository_root=repository_root,
                    label="openai.live_gate_evidence",
                )
            )
        else:
            issues.append("openai.live_smoke_status must be PENDING or PASSED")
    qwen = value["qwen"]
    if not isinstance(qwen, dict) or set(qwen) != {
        "requester_class",
        "endpoint_host_suffix",
        "api_token_environment_variable",
        "deployment_candidate",
        "paid_stage_authorization",
        "endpoint_operations_configuration",
        "compatibility_normalizer",
        "replacement_run_authorizations",
        "frozen_deployment",
        "live_smoke_status",
        "account_visible_pricing_basis",
        "live_gate_evidence",
    }:
        issues.append("qwen structure mismatch")
    else:
        if {
            "requester_class": qwen["requester_class"],
            "endpoint_host_suffix": qwen["endpoint_host_suffix"],
            "api_token_environment_variable": qwen["api_token_environment_variable"],
        } != {
            "requester_class": "QwenVllmHttpRequester",
            "endpoint_host_suffix": ".endpoints.huggingface.cloud",
            "api_token_environment_variable": "TSB_QWEN_API_TOKEN",
        }:
            issues.append("Qwen fixed configuration mismatch")
        for label in (
            "deployment_candidate",
            "paid_stage_authorization",
            "endpoint_operations_configuration",
            "compatibility_normalizer",
        ):
            issues.extend(
                _validate_path_hash(
                    qwen[label], repository_root=repository_root, label=f"qwen.{label}"
                )
            )
        replacement_paths = [
            "benchmark/config/qwen_l1_replacement_authorization_20260822_a03.json",
            "benchmark/config/qwen_l3_replacement_authorization_20260825_a02.json",
        ]
        replacement_references = qwen["replacement_run_authorizations"]
        if not isinstance(replacement_references, list) or len(replacement_references) != 2:
            issues.append("qwen.replacement_run_authorizations must contain two exact entries")
        else:
            for index, reference in enumerate(replacement_references):
                issues.extend(
                    _validate_path_hash(
                        reference,
                        repository_root=repository_root,
                        label=f"qwen.replacement_run_authorizations[{index}]",
                    )
                )
            if [reference.get("path") for reference in replacement_references] != replacement_paths:
                issues.append("qwen.replacement_run_authorizations paths mismatch")

        expected_replacements = [
            {
                "base_schedule_run_id": "pilot-L1-01-qwen2-5-coder-7b-instruct-r01-a01",
                "replacement_run_id": "pilot-L1-01-qwen2-5-coder-7b-instruct-r01-a03",
                "replacement_attempt": 3,
                "task_id": "L1-01",
                "system_id": "qwen2.5-coder-7b-instruct",
                "repetition": 1,
                "order_position": 4,
                "original_run_preserved": True,
                "original_run_validity_and_outcome_unchanged": True,
                "provider_execution_authorized_by_this_record_alone": False,
            },
            {
                "base_schedule_run_id": "pilot-L3-01-qwen2-5-coder-7b-instruct-r01-a01",
                "replacement_run_id": "pilot-L3-01-qwen2-5-coder-7b-instruct-r01-a02",
                "replacement_attempt": 2,
                "task_id": "L3-01",
                "system_id": "qwen2.5-coder-7b-instruct",
                "repetition": 1,
                "order_position": 3,
                "original_run_preserved": True,
                "original_run_validity_and_outcome_unchanged": True,
                "configuration_change_authorized": False,
                "provider_execution_authorized_by_this_record_alone": False,
            },
        ]
        if isinstance(replacement_references, list) and len(replacement_references) == 2:
            for index, (replacement_path, expected_replacement) in enumerate(
                zip(replacement_paths, expected_replacements, strict=True)
            ):
                label = f"qwen.replacement_run_authorizations[{index}]"
                try:
                    replacement = json.loads(
                        (repository_root / replacement_path).read_text(encoding="utf-8")
                    )
                    for field, expected in expected_replacement.items():
                        if replacement.get(field) != expected:
                            issues.append(f"{label}.{field} mismatch")
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    issues.append(f"{label} could not be validated: {error}")
        if qwen["compatibility_normalizer"].get("path") != (
            "benchmark/config/qwen_fenced_tool_normalizer_v3.candidate.json"
        ):
            issues.append(
                "qwen.compatibility_normalizer.path must name the reviewed Qwen normalizer candidate"
            )
        else:
            try:
                from .qwen_fenced_tool_normalizer import validate_candidate

                normalizer = json.loads(
                    (
                        repository_root
                        / "benchmark/config/qwen_fenced_tool_normalizer_v3.candidate.json"
                    ).read_text(encoding="utf-8")
                )
                issues.extend(
                    "qwen.compatibility_normalizer: " + issue
                    for issue in validate_candidate(
                        normalizer, repository_root=repository_root
                    )
                )
            except (ImportError, OSError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(
                    f"qwen.compatibility_normalizer could not be validated: {error}"
                )
        expected_endpoint_operations_path = (
            "benchmark/config/qwen_endpoint_operations.json"
        )
        if qwen["endpoint_operations_configuration"].get("path") != (
            expected_endpoint_operations_path
        ):
            issues.append(
                "qwen.endpoint_operations_configuration.path must name the frozen lifecycle configuration"
            )
        else:
            try:
                from .qwen_endpoint_operations import (
                    _load_and_validate_configuration,
                )

                _load_and_validate_configuration(
                    repository_root / expected_endpoint_operations_path,
                    repository_root
                    / "benchmark/config/qwen_deployment.candidate.json",
                )
            except (
                ImportError,
                OSError,
                RuntimeError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                issues.append(
                    f"qwen.endpoint_operations_configuration could not be validated: {error}"
                )
        expected_qwen_authorization_path = (
            "benchmark/config/qwen_budget_carry_only_20260923_l3_02_r03_gpt.json"
            if scope == "main_experiment"
            else "benchmark/config/qwen_paid_stage_authorization.json"
        )
        if qwen["paid_stage_authorization"].get("path") != expected_qwen_authorization_path:
            issues.append(
                "qwen.paid_stage_authorization.path must name the Qwen allocation authorization"
            )
        else:
            try:
                from .qwen_paid_stage_authorization import (
                    validate_qwen_paid_stage_authorization,
                )

                authorization = json.loads(
                    (repository_root / expected_qwen_authorization_path).read_text(
                        encoding="utf-8"
                    )
                )
                issues.extend(
                    "qwen.paid_stage_authorization: " + issue
                    for issue in validate_qwen_paid_stage_authorization(authorization)
                )
            except (ImportError, OSError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(
                    f"qwen.paid_stage_authorization could not be validated: {error}"
                )
        qwen_status = qwen["live_smoke_status"]
        issues.extend(
            _validate_path_hash(
                qwen["frozen_deployment"],
                repository_root=repository_root,
                label="qwen.frozen_deployment",
                allow_null=status == "CANDIDATE" and qwen_status == "PENDING",
            )
        )
        if qwen_status == "PENDING":
            if status == "FROZEN":
                issues.append("frozen Qwen live smoke and pricing evidence are required")
            if (
                qwen["account_visible_pricing_basis"] is not None
                or qwen["live_gate_evidence"] is not None
            ):
                issues.append("pending Qwen live evidence must remain null")
        elif qwen_status == "PASSED":
            try:
                from .qwen_deployment_freeze import validate_qwen_deployment_freeze

                frozen_path = repository_root / qwen["frozen_deployment"]["path"]
                frozen_deployment = json.loads(frozen_path.read_text(encoding="utf-8"))
                issues.extend(
                    "qwen.frozen_deployment: " + issue
                    for issue in validate_qwen_deployment_freeze(
                        frozen_deployment, repository_root=repository_root
                    )
                )
            except (ImportError, OSError, TypeError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(f"qwen.frozen_deployment could not be validated: {error}")
            issues.extend(
                _validate_path_hash(
                    qwen["account_visible_pricing_basis"],
                    repository_root=repository_root,
                    label="qwen.account_visible_pricing_basis",
                )
            )
            issues.extend(
                _validate_live_gate_evidence(
                    qwen["live_gate_evidence"],
                    repository_root=repository_root,
                    label="qwen.live_gate_evidence",
                )
            )
        else:
            issues.append("qwen.live_smoke_status must be PENDING or PASSED")
    expected_pending: list[str] = []
    if isinstance(openai, dict) and openai.get("live_smoke_status") == "PENDING":
        expected_pending.append(OPENAI_PENDING)
    if isinstance(qwen, dict) and qwen.get("live_smoke_status") == "PENDING":
        expected_pending.append(QWEN_PENDING)
    if value["pending_decisions"] != expected_pending:
        issues.append("pending_decisions do not match provider live-gate state")
    if status == "FROZEN" and expected_pending:
        issues.append("frozen API transport configuration cannot contain pending decisions")
    if not isinstance(value["notes"], list) or not value["notes"]:
        issues.append("notes must be a non-empty list")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the API transport configuration")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "api_transport_configuration.candidate.json",
    )
    parser.add_argument("--require-frozen", action="store_true")
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_api_transport_configuration(
        value, require_frozen=arguments.require_frozen
    )
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")


if __name__ == "__main__":
    main()
