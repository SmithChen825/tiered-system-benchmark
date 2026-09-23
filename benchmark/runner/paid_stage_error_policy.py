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
POLICY_PATH = REPOSITORY_ROOT / "benchmark" / "config" / "paid_stage_error_policy.json"


def policy_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "policy_sha256"}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_paid_stage_error_policy(value: dict[str, Any]) -> list[str]:
    if value.get("freeze_scope") == "qwen_openai_paid_main_block":
        return _validate_main_policy(value)
    if value.get("freeze_scope") == "qwen_paid_main_run":
        return _validate_qwen_main_run_policy(value)
    if value.get("freeze_scope") == "openai_paid_main_run":
        return _validate_openai_main_run_policy(value)
    expected = {
        "schema_version": "1.0.0",
        "status": "FROZEN",
        "freeze_scope": "qwen_openai_paid_pilot",
        "policy_id": "paid-stage-error-policy-20260809-v1",
        "authorized_budget_id": "qwen-openai-pilot-shared-cost-20260809-v1",
        "phases": {
            "live_gate": {
                "maximum_http_attempts_per_logical_request": 1,
                "stop_on_first_timeout_connection_or_non_2xx_response": True,
                "automatic_retry_prohibited": True,
                "reason": "promotion_and_smoke_must_pass_cleanly_before_pilot_freeze",
            },
            "pilot": {
                "maximum_http_attempts_per_logical_request": 3,
                "retryable_exception_classes": ["timeout", "connection_error"],
                "retryable_http_statuses": [408, 409, 425, 429, 500, 502, 503, 504],
                "maximum_retry_after_seconds": 30.0,
                "retry_delays_seconds": [1.0, 2.0],
                "quota_billing_spend_limit_authentication_permission_invalid_request_model_unavailable_content_policy_and_malformed_response_are_not_retryable": True,
                "stop_when_retry_policy_returns_non_retryable_or_attempts_exhausted": True,
            },
        },
        "meter_failure_rules": {
            "corrupt_unreadable_locked_or_schema_invalid_ledger_stops_before_network": True,
            "duplicate_action_id_stops_before_network": True,
            "pre_authorization_window_action_stops_before_credentials": True,
            "provider_or_combined_budget_projection_breach_stops_before_network": True,
            "missing_or_invalid_success_usage_stops": True,
            "qwen_http_without_active_runtime_clock_stops_before_network": True,
        },
        "cost_treatment": {
            "every_failed_attempt_retains_its_full_conservative_reservation": True,
            "successful_openai_attempt_reconciles_to_provider_usage": True,
            "qwen_endpoint_runtime_continues_until_scale_to_zero_is_positively_confirmed": True,
            "all_attempt_costs_count_toward_provider_and_combined_operational_stops": True,
        },
        "continuation_rules": {
            "automatic_resume_of_stopped_ledger_prohibited": True,
            "user_feedback_required_after_paid_stage_stop": True,
            "changed_configuration_requires_amendment_and_reauthorization": True,
            "successor_ledger_must_carry_forward_prior_effective_spend_and_audit_link": True,
            "main_experiment_included": False,
        },
    }
    if set(value) != set(expected) | {"policy_sha256"}:
        return ["paid-stage error policy fields mismatch"]
    issues = []
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            issues.append(f"{key} mismatch")
    digest = value.get("policy_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("policy_sha256 must be a lowercase SHA-256")
    elif digest != policy_sha256(value):
        issues.append("policy_sha256 mismatch")
    return issues


def _validate_main_policy(value: dict[str, Any]) -> list[str]:
    expected = {
        "schema_version": "1.1.0",
        "status": "FROZEN",
        "freeze_scope": "qwen_openai_paid_main_block",
        "policy_id": "paid-main-error-policy-l1-01-r01-20260901-v1",
        "authorized_budget_id": "qwen-openai-main-l1-01-r01-20260901-v1",
        "phases": {
            "main": {
                "maximum_http_attempts_per_logical_request": 3,
                "retryable_exception_classes": ["timeout", "connection_error"],
                "retryable_http_statuses": [408, 409, 425, 429, 500, 502, 503, 504],
                "maximum_retry_after_seconds": 30.0,
                "retry_delays_seconds": [1.0, 2.0],
                "quota_billing_spend_limit_authentication_permission_invalid_request_model_unavailable_content_policy_and_malformed_response_are_not_retryable": True,
                "stop_when_retry_policy_returns_non_retryable_or_attempts_exhausted": True,
            }
        },
        "meter_failure_rules": {
            "corrupt_unreadable_locked_or_schema_invalid_ledger_stops_before_network": True,
            "duplicate_action_id_stops_before_network": True,
            "pre_authorization_window_action_stops_before_credentials": True,
            "provider_or_combined_budget_projection_breach_stops_before_network": True,
            "missing_or_invalid_success_usage_stops": True,
            "qwen_http_without_active_runtime_clock_stops_before_network": True,
        },
        "cost_treatment": {
            "every_failed_attempt_retains_its_full_conservative_reservation": True,
            "successful_openai_attempt_reconciles_to_provider_usage": True,
            "qwen_endpoint_runtime_continues_until_scale_to_zero_is_positively_confirmed": True,
            "all_attempt_costs_count_toward_provider_and_combined_operational_stops": True,
        },
        "continuation_rules": {
            "automatic_resume_of_stopped_ledger_prohibited": True,
            "user_feedback_required_after_paid_stage_stop": True,
            "changed_configuration_requires_amendment_and_reauthorization": True,
            "successor_ledger_must_carry_forward_prior_effective_spend_and_audit_link": True,
            "authorization_limited_to_block_id": "L1-01-r01",
            "main_experiment_included": True,
        },
    }
    if set(value) != set(expected) | {"policy_sha256"}:
        return ["paid-stage error policy fields mismatch"]
    issues = [f"{key} mismatch" for key, wanted in expected.items() if value.get(key) != wanted]
    digest = value.get("policy_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("policy_sha256 must be a lowercase SHA-256")
    elif digest != policy_sha256(value):
        issues.append("policy_sha256 mismatch")
    return issues


def _validate_qwen_main_run_policy(value: dict[str, Any]) -> list[str]:
    variants = {
        "paid-main-error-policy-l1-01-r02-qwen-20260907-v1": {
            "budget_id": "qwen-openai-main-l1-01-r01-20260901-v1",
            "run_id": "main-L1-01-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L1-01-r02",
        },
        "paid-main-error-policy-l1-01-r03-qwen-20260909-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-01-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L1-01-r03",
        },
        "paid-main-error-policy-l1-02-r01-qwen-20260910-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L1-02-r01",
        },
        "paid-main-error-policy-l1-02-r02-qwen-20260911-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L1-02-r02",
        },
        "paid-main-error-policy-l1-02-r03-qwen-20260912-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L1-02-r03",
        },
        "paid-main-error-policy-l1-03-r01-qwen-20260912-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L1-03-r01",
        },
        "paid-main-error-policy-l1-03-r02-qwen-20260914-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L1-03-r02",
        },
        "paid-main-error-policy-l1-03-r03-qwen-20260916-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L1-03-r03",
        },
        "paid-main-error-policy-l2-01-r01-qwen-20260916-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L2-01-r01",
        },
        "paid-main-error-policy-l2-01-r02-qwen-20260917-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L2-01-r02",
        },
        "paid-main-error-policy-l2-01-r03-qwen-20260917-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L2-01-r03",
        },
        "paid-main-error-policy-l2-02-r01-qwen-20260919-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L2-02-r01",
        },
        "paid-main-error-policy-l2-02-r02-qwen-20260919-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L2-02-r02",
        },
        "paid-main-error-policy-l2-02-r03-qwen-20260920-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L2-02-r03",
        },
        "paid-main-error-policy-l2-03-r01-qwen-20260920-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L2-03-r01",
        },
        "paid-main-error-policy-l2-03-r02-qwen-20260921-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L2-03-r02",
        },
        "paid-main-error-policy-l2-03-r03-qwen-20260921-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L2-03-r03",
        },
        "paid-main-error-policy-l3-01-r01-qwen-20260922-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L3-01-r01",
        },
        "paid-main-error-policy-l3-01-r03-qwen-20260922-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L3-01-r03",
        },
        "paid-main-error-policy-l3-02-r03-qwen-20260923-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r03-a01",
            "block_id": "L3-02-r03",
        },
        "paid-main-error-policy-l3-02-r02-qwen-20260923-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L3-02-r02",
        },
        "paid-main-error-policy-l3-02-r01-qwen-20260923-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r01-a01",
            "block_id": "L3-02-r01",
        },
        "paid-main-error-policy-l3-01-r02-qwen-20260922-v1": {
            "budget_id": "qwen-openai-main-l1-01-r02-a02-20260908-v1",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r02-a01",
            "block_id": "L3-01-r02",
        },
    }
    variant = variants.get(value.get("policy_id"))
    if variant is None:
        return ["unsupported Qwen main-run policy_id"]
    expected = {
        "schema_version": "1.1.0",
        "status": "FROZEN",
        "freeze_scope": "qwen_paid_main_run",
        "policy_id": value.get("policy_id"),
        "authorized_budget_id": variant["budget_id"],
        "authorized_run_ids": [variant["run_id"]],
        "phases": {
            "main": {
                "maximum_http_attempts_per_logical_request": 3,
                "retryable_exception_classes": ["timeout", "connection_error"],
                "retryable_http_statuses": [408, 409, 425, 429, 500, 502, 503, 504],
                "maximum_retry_after_seconds": 30.0,
                "retry_delays_seconds": [1.0, 2.0],
                "quota_billing_spend_limit_authentication_permission_invalid_request_model_unavailable_content_policy_and_malformed_response_are_not_retryable": True,
                "stop_when_retry_policy_returns_non_retryable_or_attempts_exhausted": True,
            }
        },
        "meter_failure_rules": {
            "corrupt_unreadable_locked_or_schema_invalid_ledger_stops_before_network": True,
            "duplicate_action_id_stops_before_network": True,
            "pre_authorization_window_action_stops_before_credentials": True,
            "provider_or_combined_budget_projection_breach_stops_before_network": True,
            "missing_or_invalid_success_usage_stops": True,
            "qwen_http_without_active_runtime_clock_stops_before_network": True,
        },
        "cost_treatment": {
            "every_failed_attempt_retains_its_full_conservative_reservation": True,
            "successful_openai_attempt_reconciles_to_provider_usage": True,
            "qwen_endpoint_runtime_continues_until_scale_to_zero_is_positively_confirmed": True,
            "all_attempt_costs_count_toward_provider_and_combined_operational_stops": True,
        },
        "continuation_rules": {
            "automatic_resume_of_stopped_ledger_prohibited": True,
            "user_feedback_required_after_paid_stage_stop": True,
            "changed_configuration_requires_amendment_and_reauthorization": True,
            "successor_ledger_must_carry_forward_prior_effective_spend_and_audit_link": True,
            "authorization_limited_to_block_id": variant["block_id"],
            "authorization_limited_to_exact_run_ids": True,
            "openai_provider_calls_authorized": False,
            "main_experiment_included": True,
        },
        "policy_sha256": value.get("policy_sha256"),
    }
    if set(value) != set(expected):
        return ["paid-stage Qwen main-run error policy fields mismatch"]
    issues = [
        f"{key} mismatch"
        for key, wanted in expected.items()
        if key != "policy_sha256" and value.get(key) != wanted
    ]
    digest = value.get("policy_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("policy_sha256 must be a lowercase SHA-256")
    elif digest != policy_sha256(value):
        issues.append("policy_sha256 mismatch")
    return issues


def _validate_openai_main_run_policy(value: dict[str, Any]) -> list[str]:
    is_l301_r02 = value.get("policy_id") == "paid-main-error-policy-l3-01-r02-openai-20260922-v1"
    is_l302_r01 = value.get("policy_id") == "paid-main-error-policy-l3-02-r01-openai-20260923-v1"
    is_l302_r02 = value.get("policy_id") == "paid-main-error-policy-l3-02-r02-openai-20260923-v1"
    is_l302_r03 = value.get("policy_id") == "paid-main-error-policy-l3-02-r03-openai-20260923-v1"
    is_l301_r03 = value.get("policy_id") == "paid-main-error-policy-l3-01-r03-openai-20260922-v1"
    is_l301_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l3-01-r01-openai-20260922-v1"
    )
    is_l203_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l2-03-r03-openai-20260921-v1"
    )
    is_l203_r02 = value.get("policy_id") == (
        "paid-main-error-policy-l2-03-r02-openai-20260921-v1"
    )
    is_l203_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l2-03-r01-openai-20260920-v1"
    )
    is_l202_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l2-02-r03-openai-20260920-v1"
    )
    is_l202_r02 = value.get("policy_id") == (
        "paid-main-error-policy-l2-02-r02-openai-20260919-v1"
    )
    is_l202_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l2-02-r01-openai-20260919-v1"
    )
    is_l201_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l2-01-r03-openai-20260917-v1"
    )
    is_l201_r02 = value.get("policy_id") == (
        "paid-main-error-policy-l2-01-r02-openai-20260917-v1"
    )
    is_l201_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l2-01-r01-openai-20260916-v1"
    )
    is_l103_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l1-03-r03-openai-20260914-v1"
    )
    is_l103_r02_a02 = value.get("policy_id") == (
        "paid-main-error-policy-l1-03-r02-openai-a02-20260914-v1"
    )
    is_l103_r02 = value.get("policy_id") == (
        "paid-main-error-policy-l1-03-r02-openai-20260914-v1"
    )
    is_l103_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l1-03-r01-openai-20260913-v1"
    )
    is_l102_r01 = value.get("policy_id") == (
        "paid-main-error-policy-l1-02-r01-openai-20260910-v1"
    )
    is_l102_r02 = value.get("policy_id") == (
        "paid-main-error-policy-l1-02-r02-openai-20260911-v1"
    )
    is_l102_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l1-02-r03-openai-20260912-v1"
    )
    is_l102 = is_l102_r01 or is_l102_r02 or is_l102_r03
    is_r03 = value.get("policy_id") == (
        "paid-main-error-policy-l1-01-r03-openai-20260909-v1"
    )
    attempt = 3 if value.get("policy_id") == (
        "paid-main-error-policy-l1-01-r02-openai-a03-20260908-v1"
    ) else 2 if value.get("policy_id") == (
        "paid-main-error-policy-l1-01-r02-openai-a02-20260908-v1"
    ) else 1
    expected = {
        "schema_version": "1.1.0",
        "status": "FROZEN",
        "freeze_scope": "openai_paid_main_run",
        "policy_id": (
            "paid-main-error-policy-l3-01-r02-openai-20260922-v1" if is_l301_r02 else "paid-main-error-policy-l3-02-r01-openai-20260923-v1" if is_l302_r01 else "paid-main-error-policy-l3-02-r03-openai-20260923-v1" if is_l302_r03 else "paid-main-error-policy-l3-02-r02-openai-20260923-v1" if is_l302_r02 else "paid-main-error-policy-l3-01-r03-openai-20260922-v1" if is_l301_r03 else "paid-main-error-policy-l3-01-r01-openai-20260922-v1" if is_l301_r01
            else "paid-main-error-policy-l2-03-r03-openai-20260921-v1" if is_l203_r03
            else "paid-main-error-policy-l2-03-r02-openai-20260921-v1" if is_l203_r02
            else "paid-main-error-policy-l2-03-r01-openai-20260920-v1" if is_l203_r01
            else "paid-main-error-policy-l2-02-r03-openai-20260920-v1" if is_l202_r03
            else "paid-main-error-policy-l2-02-r02-openai-20260919-v1" if is_l202_r02
            else "paid-main-error-policy-l2-02-r01-openai-20260919-v1" if is_l202_r01
            else "paid-main-error-policy-l2-01-r03-openai-20260917-v1" if is_l201_r03
            else "paid-main-error-policy-l2-01-r02-openai-20260917-v1" if is_l201_r02
            else "paid-main-error-policy-l2-01-r01-openai-20260916-v1" if is_l201_r01
            else "paid-main-error-policy-l1-03-r03-openai-20260914-v1" if is_l103_r03
            else "paid-main-error-policy-l1-03-r02-openai-a02-20260914-v1" if is_l103_r02_a02
            else "paid-main-error-policy-l1-03-r02-openai-20260914-v1" if is_l103_r02
            else "paid-main-error-policy-l1-03-r01-openai-20260913-v1" if is_l103_r01
            else "paid-main-error-policy-l1-02-r03-openai-20260912-v1" if is_l102_r03
            else "paid-main-error-policy-l1-02-r02-openai-20260911-v1" if is_l102_r02
            else "paid-main-error-policy-l1-02-r01-openai-20260910-v1" if is_l102_r01
            else "paid-main-error-policy-l1-01-r03-openai-20260909-v1" if is_r03
            else f"paid-main-error-policy-l1-01-r02-openai-a{attempt:02d}-20260908-v1"
            if attempt > 1 else "paid-main-error-policy-l1-01-r02-openai-20260908-v1"
        ),
        "authorized_budget_id": (
            "qwen-openai-main-l1-01-r02-a02-20260908-v1"
            if is_l302_r03 or is_l302_r02 or is_l302_r01 or is_l301_r03 or is_l301_r02 or is_l301_r01 or is_l203_r03 or is_l203_r02 or is_l203_r01 or is_l202_r03 or is_l202_r02 or is_l202_r01 or is_l201_r03 or is_l201_r02 or is_l201_r01 or is_l103_r03 or is_l103_r02_a02 or is_l103_r02 or is_l103_r01 or is_l102 or is_r03 or attempt > 1 else "qwen-openai-main-l1-01-r01-20260901-v1"
        ),
        "authorized_run_ids": [
            "main-L3-01-gpt-5-4-r02-a01" if is_l301_r02 else "main-L3-02-gpt-5-4-r01-a01" if is_l302_r01 else "main-L3-02-gpt-5-4-r03-a01" if is_l302_r03 else "main-L3-02-gpt-5-4-r02-a01" if is_l302_r02 else "main-L3-01-gpt-5-4-r03-a01" if is_l301_r03 else "main-L3-01-gpt-5-4-r01-a01" if is_l301_r01
            else "main-L2-03-gpt-5-4-r03-a01" if is_l203_r03
            else "main-L2-03-gpt-5-4-r02-a01" if is_l203_r02
            else "main-L2-03-gpt-5-4-r01-a01" if is_l203_r01
            else "main-L2-02-gpt-5-4-r03-a01" if is_l202_r03
            else "main-L2-02-gpt-5-4-r02-a01" if is_l202_r02
            else "main-L2-02-gpt-5-4-r01-a01" if is_l202_r01
            else "main-L2-01-gpt-5-4-r03-a01" if is_l201_r03
            else "main-L2-01-gpt-5-4-r02-a01" if is_l201_r02
            else "main-L2-01-gpt-5-4-r01-a01" if is_l201_r01
            else "main-L1-03-gpt-5-4-r03-a01" if is_l103_r03
            else "main-L1-03-gpt-5-4-r02-a02" if is_l103_r02_a02
            else "main-L1-03-gpt-5-4-r02-a01" if is_l103_r02
            else "main-L1-03-gpt-5-4-r01-a01" if is_l103_r01
            else "main-L1-02-gpt-5-4-r03-a01" if is_l102_r03
            else "main-L1-02-gpt-5-4-r02-a01" if is_l102_r02
            else "main-L1-02-gpt-5-4-r01-a01" if is_l102_r01
            else "main-L1-01-gpt-5-4-r03-a01" if is_r03
            else f"main-L1-01-gpt-5-4-r02-a{attempt:02d}" if attempt > 1
            else "main-L1-01-gpt-5-4-r02-a01"
        ],
        "phases": {
            "main": {
                "maximum_http_attempts_per_logical_request": 3,
                "retryable_exception_classes": ["timeout", "connection_error"],
                "retryable_http_statuses": [408, 409, 425, 429, 500, 502, 503, 504],
                "maximum_retry_after_seconds": 30.0,
                "retry_delays_seconds": [1.0, 2.0],
                "quota_billing_spend_limit_authentication_permission_invalid_request_model_unavailable_content_policy_and_malformed_response_are_not_retryable": True,
                "stop_when_retry_policy_returns_non_retryable_or_attempts_exhausted": True,
            }
        },
        "meter_failure_rules": {
            "corrupt_unreadable_locked_or_schema_invalid_ledger_stops_before_network": True,
            "duplicate_action_id_stops_before_network": True,
            "pre_authorization_window_action_stops_before_credentials": True,
            "provider_or_combined_budget_projection_breach_stops_before_network": True,
            "missing_or_invalid_success_usage_stops": True,
            "qwen_http_without_active_runtime_clock_stops_before_network": True,
        },
        "cost_treatment": {
            "every_failed_attempt_retains_its_full_conservative_reservation": True,
            "successful_openai_attempt_reconciles_to_provider_usage": True,
            "qwen_endpoint_runtime_continues_until_scale_to_zero_is_positively_confirmed": True,
            "all_attempt_costs_count_toward_provider_and_combined_operational_stops": True,
        },
        "continuation_rules": {
            "automatic_resume_of_stopped_ledger_prohibited": True,
            "user_feedback_required_after_paid_stage_stop": True,
            "changed_configuration_requires_amendment_and_reauthorization": True,
            "successor_ledger_must_carry_forward_prior_effective_spend_and_audit_link": True,
            "authorization_limited_to_block_id": "L3-01-r02" if is_l301_r02 else "L3-02-r01" if is_l302_r01 else "L3-02-r03" if is_l302_r03 else "L3-02-r02" if is_l302_r02 else "L3-01-r03" if is_l301_r03 else "L3-01-r01" if is_l301_r01 else "L2-03-r03" if is_l203_r03 else "L2-03-r02" if is_l203_r02 else "L2-03-r01" if is_l203_r01 else "L2-02-r03" if is_l202_r03 else "L2-02-r02" if is_l202_r02 else "L2-02-r01" if is_l202_r01 else "L2-01-r03" if is_l201_r03 else "L2-01-r02" if is_l201_r02 else "L2-01-r01" if is_l201_r01 else "L1-03-r03" if is_l103_r03 else "L1-03-r02" if is_l103_r02_a02 or is_l103_r02 else "L1-03-r01" if is_l103_r01 else "L1-02-r03" if is_l102_r03 else "L1-02-r02" if is_l102_r02 else "L1-02-r01" if is_l102_r01 else "L1-01-r03" if is_r03 else "L1-01-r02",
            "authorization_limited_to_exact_run_ids": True,
            "qwen_provider_calls_authorized": False,
            "main_experiment_included": True,
        },
        "policy_sha256": value.get("policy_sha256"),
    }
    if set(value) != set(expected):
        return ["paid-stage OpenAI main-run error policy fields mismatch"]
    issues = [
        f"{key} mismatch"
        for key, wanted in expected.items()
        if key != "policy_sha256" and value.get(key) != wanted
    ]
    digest = value.get("policy_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("policy_sha256 must be a lowercase SHA-256")
    elif digest != policy_sha256(value):
        issues.append("policy_sha256 mismatch")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate paid-stage error policy")
    parser.add_argument("path", nargs="?", type=Path, default=POLICY_PATH)
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_paid_stage_error_policy(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")
    print(f"policy_sha256={value['policy_sha256']}")


if __name__ == "__main__":
    main()
