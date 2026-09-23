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
EXPECTED_TASKS = ["L1-01", "L2-02", "L3-01", "L4-01"]


def authorization_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "authorization_sha256"}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_qwen_paid_stage_authorization(value: dict[str, Any]) -> list[str]:
    if value.get("authorization_id") in {
        "qwen-carry-only-l1-01-r02-20260908-v1",
        "qwen-carry-only-l1-01-r02-a02-20260908-v1",
        "qwen-carry-only-l1-01-r02-a03-20260908-v1",
        "qwen-carry-only-l1-01-r03-20260909-v1",
        "qwen-carry-only-l1-02-r01-20260910-v1",
        "qwen-carry-only-l1-02-r02-gpt-20260911-v1",
        "qwen-carry-only-l1-02-r03-gpt-20260912-v1",
        "qwen-carry-only-l1-03-r01-gpt-20260913-v1",
        "qwen-carry-only-l1-03-r02-gpt-20260914-v1",
        "qwen-carry-only-l1-03-r02-gpt-a02-20260914-v1",
        "qwen-carry-only-l1-03-r03-gpt-20260914-v1",
        "qwen-carry-only-l2-01-r01-gpt-20260916-v1",
        "qwen-carry-only-l2-01-r02-gpt-20260917-v1",
        "qwen-carry-only-l2-01-r03-gpt-20260917-v1",
        "qwen-carry-only-l2-02-r01-gpt-20260919-v1",
        "qwen-carry-only-l2-02-r02-gpt-20260919-v1",
        "qwen-carry-only-l2-02-r03-gpt-20260920-v1",
        "qwen-carry-only-l2-03-r01-gpt-20260920-v1",
        "qwen-carry-only-l2-03-r02-gpt-20260921-v1",
        "qwen-carry-only-l2-03-r03-gpt-20260921-v1",
        "qwen-carry-only-l3-01-r01-gpt-20260922-v1",
        "qwen-carry-only-l3-01-r03-gpt-20260922-v1",
        "qwen-carry-only-l3-02-r02-gpt-20260923-v1",
        "qwen-carry-only-l3-02-r03-gpt-20260923-v1",
        "qwen-carry-only-l3-02-r01-gpt-20260923-v1",
        "qwen-carry-only-l3-01-r02-gpt-20260922-v1",
    }:
        return _validate_main_carry_only_authorization(value)
    if value.get("authorization_id") in {
        "qwen-main-l1-01-r01-20260901-v1",
        "qwen-main-l1-01-r02-20260907-v1",
        "qwen-main-l1-01-r03-20260909-v1",
        "qwen-main-l1-02-r01-20260910-v1",
        "qwen-main-l1-02-r02-20260911-v1",
        "qwen-main-l1-02-r03-20260912-v1",
        "qwen-main-l1-03-r01-20260912-v1",
        "qwen-main-l1-03-r02-20260914-v1",
        "qwen-main-l1-03-r03-20260916-v1",
        "qwen-main-l2-01-r01-20260916-v1",
        "qwen-main-l2-01-r02-20260917-v1",
        "qwen-main-l2-01-r03-20260917-v1",
        "qwen-main-l2-02-r01-20260919-v1",
        "qwen-main-l2-02-r02-20260919-v1",
        "qwen-main-l2-02-r03-20260920-v1",
        "qwen-main-l2-03-r01-20260920-v1",
        "qwen-main-l2-03-r02-20260921-v1",
        "qwen-main-l2-03-r03-20260921-v1",
        "qwen-main-l3-01-r01-20260922-v1",
        "qwen-main-l3-01-r03-20260922-v1",
        "qwen-main-l3-02-r03-20260923-v1",
        "qwen-main-l3-02-r02-20260923-v1",
        "qwen-main-l3-02-r01-20260923-v1",
        "qwen-main-l3-01-r02-20260922-v1",
    }:
        return _validate_main_authorization(value)
    issues: list[str] = []
    expected_top = {
        "schema_version",
        "status",
        "authorization_id",
        "authorized_on",
        "timezone",
        "scope",
        "combined_two_provider_budget",
        "authorization_boundaries",
        "cost_controls",
        "time_controls",
        "failure_policy",
        "official_sources",
        "authorization_sha256",
    }
    if set(value) != expected_top:
        return [f"top-level fields must equal {sorted(expected_top)}"]
    if value["schema_version"] != "1.0.0":
        issues.append("schema_version must be 1.0.0")
    if value["status"] != "APPROVED_PENDING_EXTERNAL_GATES":
        issues.append("status must remain APPROVED_PENDING_EXTERNAL_GATES")
    if value["authorization_id"] != "qwen-live-promotion-pilot-cost-20260811-v4":
        issues.append("authorization_id mismatch")
    if value["authorized_on"] != "2026-08-11":
        issues.append("authorized_on mismatch")
    if value["timezone"] != "Australia/Sydney":
        issues.append("timezone mismatch")

    if value["scope"] != {
        "provider": "hugging_face_inference_endpoints_dedicated",
        "deployment_candidate_id": "qwen-deployment-candidate-20260811-r4",
        "included_phases": ["live_promotion", "qwen_four_task_pilot"],
        "pilot_task_ids": EXPECTED_TASKS,
        "pilot_run_count": 4,
        "main_experiment_included": False,
    }:
        issues.append("scope must remain limited to live promotion and four Qwen pilot runs")

    combined = value["combined_two_provider_budget"]
    expected_combined = {
        "authorization_id": "qwen-openai-pilot-shared-cost-20260809-v1",
        "currency": "USD",
        "hard_budget_usd": 20.0,
        "operational_stop_threshold_usd": 18.0,
        "reserve_usd": 2.0,
        "qwen_hard_allocation_usd": 12.0,
        "qwen_operational_stop_usd": 11.0,
        "qwen_reserve_usd": 1.0,
        "openai_hard_allocation_usd": 8.0,
        "openai_operational_stop_usd": 7.0,
        "openai_reserve_usd": 1.0,
        "combined_meter_must_aggregate_both_providers_before_each_next_paid_action": True,
        "automatic_reallocation_between_providers_prohibited": True,
        "reallocation_requires_user_feedback_and_reauthorization": True,
        "main_experiment_included": False,
    }
    if combined != expected_combined:
        issues.append("combined two-provider budget mismatch")
    elif (
        combined["qwen_hard_allocation_usd"] + combined["openai_hard_allocation_usd"]
        != combined["hard_budget_usd"]
        or combined["qwen_operational_stop_usd"] + combined["openai_operational_stop_usd"]
        != combined["operational_stop_threshold_usd"]
        or combined["qwen_reserve_usd"] + combined["openai_reserve_usd"]
        != combined["reserve_usd"]
    ):
        issues.append("provider allocations must sum to the shared USD 20/18/2 budget")

    if value["authorization_boundaries"] != {
        "not_before": "2026-08-11T16:15:00+10:00",
        "promotion_only_may_precede_complete_experiment_freeze": True,
        "benchmark_task_calls_require_complete_frozen_experiment_manifest": True,
        "credentials_must_be_runtime_only": True,
        "secrets_must_not_enter_evidence_or_configuration": True,
    }:
        issues.append("authorization boundaries mismatch")

    cost = value["cost_controls"]
    expected_cost = {
        "currency": "USD",
        "hard_budget_usd": 12.0,
        "operational_stop_threshold_usd": 11.0,
        "reserve_for_billing_lag_and_rounding_usd": 1.0,
        "public_reference_hourly_rate_usd": 0.8,
        "provider_billing_basis": "per_minute_while_initializing_or_running",
        "provider_enforced_spending_cap_available": False,
        "final_invoice_may_exceed_operational_estimate_due_to_billing_lag_or_rounding": True,
        "account_visible_rate_must_be_captured_before_creation": True,
        "maximum_running_replicas": 1,
        "maximum_cumulative_endpoint_running_hours": 12.0,
        "cost_estimate_rule": "maximum_of_account_visible_accrued_cost_and_each_initializing_or_running_segment_rounded_up_to_started_provider_billing_minutes_times_account_visible_rate",
        "stop_at_earliest_cost_or_time_limit": True,
        "additional_paid_resources_prohibited": True,
    }
    if cost != expected_cost:
        issues.append("cost controls must preserve Qwen's USD 12 allocation and USD 11 stop")
    elif cost["operational_stop_threshold_usd"] + cost["reserve_for_billing_lag_and_rounding_usd"] != cost["hard_budget_usd"]:
        issues.append("operational threshold plus reserve must equal the hard budget")

    time_controls = value["time_controls"]
    expected_time = {
        "pilot_task_limit_seconds": 5400,
        "qwen_pilot_task_count": 4,
        "maximum_timed_pilot_task_seconds": 21600,
        "maximum_live_promotion_operator_seconds": 21600,
        "maximum_cumulative_endpoint_running_seconds": 43200,
        "scale_to_zero_timeout_minutes": 15,
        "stop_and_request_feedback_when_limit_reached": True,
    }
    if time_controls != expected_time:
        issues.append("time controls mismatch")
    elif time_controls["pilot_task_limit_seconds"] * time_controls["qwen_pilot_task_count"] != time_controls["maximum_timed_pilot_task_seconds"]:
        issues.append("timed pilot ceiling must equal four task limits")
    elif time_controls["maximum_cumulative_endpoint_running_seconds"] != int(cost.get("maximum_cumulative_endpoint_running_hours", -1) * 3600):
        issues.append("endpoint running hour and second ceilings disagree")

    if value["failure_policy"] != {
        "stop_on_first_failed_or_unavailable_live_gate": True,
        "automatic_region_hardware_model_runtime_context_or_parser_substitution_prohibited": True,
        "candidate_amendment_and_user_feedback_required_before_retry_with_changed_configuration": True,
        "pilot_runs_prohibited_until_all_live_gates_pass_and_the_pilot_manifest_is_frozen": True,
        "final_required_provider_state": "scaled_to_zero_and_verified",
    }:
        issues.append("failure policy must remain fail closed")

    if value["official_sources"] != [
        "https://huggingface.co/docs/inference-endpoints/pricing",
        "https://huggingface.co/docs/hub/en/billing",
    ]:
        issues.append("official cost sources mismatch")

    digest = value["authorization_sha256"]
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("authorization_sha256 must be a lowercase SHA-256")
    elif digest != authorization_sha256(value):
        issues.append("authorization_sha256 does not match canonical content")
    return issues


def _validate_main_authorization(value: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_top = {
        "schema_version", "status", "authorization_id", "authorized_on",
        "timezone", "scope", "combined_two_provider_budget",
        "authorization_boundaries", "cost_controls", "time_controls",
        "failure_policy", "official_sources", "authorization_sha256",
    }
    if set(value) != expected_top:
        return [f"top-level fields must equal {sorted(expected_top)}"]
    variants = {
        "qwen-main-l1-01-r01-20260901-v1": {
            "authorized_on": "2026-09-01",
            "not_before": "2026-09-01T12:36:02+10:00",
            "block_id": "L1-01-r01",
            "run_id": "main-L1-01-qwen2-5-coder-7b-instruct-r01-a01",
        },
        "qwen-main-l1-01-r02-20260907-v1": {
            "authorized_on": "2026-09-07",
            "not_before": "2026-09-07T13:57:43+10:00",
            "block_id": "L1-01-r02",
            "run_id": "main-L1-01-qwen2-5-coder-7b-instruct-r02-a01",
        },
        "qwen-main-l1-01-r03-20260909-v1": {
            "authorized_on": "2026-09-09",
            "not_before": "2026-09-09T12:00:15+10:00",
            "block_id": "L1-01-r03",
            "run_id": "main-L1-01-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-02-r01-20260910-v1": {
            "authorized_on": "2026-09-10",
            "not_before": "2026-09-10T15:01:59+10:00",
            "block_id": "L1-02-r01",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-02-r02-20260911-v1": {
            "authorized_on": "2026-09-11",
            "not_before": "2026-09-11T10:18:06+10:00",
            "block_id": "L1-02-r02",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-02-r03-20260912-v1": {
            "authorized_on": "2026-09-12",
            "not_before": "2026-09-12T10:53:45+10:00",
            "block_id": "L1-02-r03",
            "run_id": "main-L1-02-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-03-r01-20260912-v1": {
            "authorized_on": "2026-09-12",
            "not_before": "2026-09-12T21:04:53+10:00",
            "block_id": "L1-03-r01",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-03-r02-20260914-v1": {
            "authorized_on": "2026-09-14",
            "not_before": "2026-09-14T10:03:00+10:00",
            "block_id": "L1-03-r02",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l1-03-r03-20260916-v1": {
            "authorized_on": "2026-09-16",
            "not_before": "2026-09-16T16:35:04+10:00",
            "block_id": "L1-03-r03",
            "run_id": "main-L1-03-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-01-r01-20260916-v1": {
            "authorized_on": "2026-09-16",
            "not_before": "2026-09-16T19:55:41+10:00",
            "block_id": "L2-01-r01",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-01-r02-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T13:02:00+10:00",
            "block_id": "L2-01-r02",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-01-r03-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T23:00:00+10:00",
            "block_id": "L2-01-r03",
            "run_id": "main-L2-01-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-02-r01-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T11:35:49+10:00",
            "block_id": "L2-02-r01",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-02-r02-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T15:04:38+10:00",
            "block_id": "L2-02-r02",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-02-r03-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T14:08:05+10:00",
            "block_id": "L2-02-r03",
            "run_id": "main-L2-02-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-03-r01-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T23:59:49+10:00",
            "block_id": "L2-03-r01",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-03-r02-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T16:07:15+10:00",
            "block_id": "L2-03-r02",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l2-03-r03-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T22:53:25+10:00",
            "block_id": "L2-03-r03",
            "run_id": "main-L2-03-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-01-r01-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T17:16:29+10:00",
            "block_id": "L3-01-r01",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-01-r03-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T21:40:22+10:00",
            "block_id": "L3-01-r03",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-02-r03-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T13:10:13+10:00",
            "block_id": "L3-02-r03",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r03-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-02-r02-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T11:12:46+10:00",
            "block_id": "L3-02-r02",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-02-r01-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T10:32:30+10:00",
            "block_id": "L3-02-r01",
            "run_id": "main-L3-02-qwen2-5-coder-7b-instruct-r01-a01",
            "expanded_budget": True,
        },
        "qwen-main-l3-01-r02-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T18:55:11+10:00",
            "block_id": "L3-01-r02",
            "run_id": "main-L3-01-qwen2-5-coder-7b-instruct-r02-a01",
            "expanded_budget": True,
        },
    }
    variant = variants.get(value.get("authorization_id"))
    if variant is None:
        return ["unsupported main authorization_id"]
    expanded_budget = variant.get("expanded_budget") is True
    combined_budget = {
        "authorization_id": (
            "qwen-openai-main-l1-01-r02-a02-20260908-v1"
            if expanded_budget else "qwen-openai-main-l1-01-r01-20260901-v1"
        ),
        "currency": "USD", "hard_budget_usd": 5.0 if expanded_budget else 3.0,
        "operational_stop_threshold_usd": 4.2 if expanded_budget else 2.5,
        "reserve_usd": 0.8 if expanded_budget else 0.5,
        "qwen_hard_allocation_usd": 2.5, "qwen_operational_stop_usd": 2.1,
        "qwen_reserve_usd": 0.4,
        "openai_hard_allocation_usd": 2.5 if expanded_budget else 0.5,
        "openai_operational_stop_usd": 2.1 if expanded_budget else 0.4,
        "openai_reserve_usd": 0.4 if expanded_budget else 0.1,
        "combined_meter_must_aggregate_both_providers_before_each_next_paid_action": True,
        "automatic_reallocation_between_providers_prohibited": True,
        "reallocation_requires_user_feedback_and_reauthorization": True,
        "main_experiment_included": True,
    }
    if expanded_budget:
        combined_budget["supersedes_authorization_id"] = (
            "qwen-openai-main-l1-01-r01-20260901-v1"
        )
    expected = {
        "schema_version": "1.1.0",
        "status": "APPROVED_PENDING_EXTERNAL_GATES",
        "authorized_on": variant["authorized_on"], "timezone": "Australia/Sydney",
        "scope": {
            "provider": "hugging_face_inference_endpoints_dedicated",
            "deployment_candidate_id": "qwen-deployment-candidate-20260811-r4",
            "included_phase": "main", "block_id": variant["block_id"],
            "authorized_run_ids": [variant["run_id"]],
            "main_experiment_included": True, "other_main_runs_included": False,
        },
        "combined_two_provider_budget": combined_budget,
        "authorization_boundaries": {
            "not_before": variant["not_before"],
            "benchmark_task_calls_require_complete_frozen_main_manifest": True,
            "fresh_main_ledger_required": True,
            "account_visible_starting_balance_evidence_required_before_endpoint_creation": True,
            "credentials_must_be_runtime_only": True,
            "secrets_must_not_enter_evidence_or_configuration": True,
        },
        "cost_controls": {
            "currency": "USD", "hard_budget_usd": 2.5,
            "operational_stop_threshold_usd": 2.1,
            "reserve_for_billing_lag_and_rounding_usd": 0.4,
            "public_reference_hourly_rate_usd": 0.8,
            "provider_billing_basis": "per_minute_while_initializing_or_running",
            "provider_enforced_spending_cap_available": False,
            "account_visible_rate_must_be_captured_before_creation": True,
            "maximum_running_replicas": 1,
            "maximum_cumulative_endpoint_running_hours": 2.625,
            "stop_at_earliest_cost_or_time_limit": True,
            "additional_paid_resources_prohibited": True,
        },
        "time_controls": {
            "main_task_limit_seconds": 5400, "authorized_run_count": 1,
            "maximum_timed_task_seconds": 5400,
            "maximum_cumulative_endpoint_running_seconds": 9450,
            "scale_to_zero_timeout_minutes": 15,
            "stop_and_request_feedback_when_limit_reached": True,
        },
        "failure_policy": {
            "stop_on_first_failed_or_unavailable_live_gate": True,
            "automatic_region_hardware_model_runtime_context_or_parser_substitution_prohibited": True,
            "candidate_amendment_and_user_feedback_required_before_retry_with_changed_configuration": True,
            "authorization_expires_after_the_listed_run_or_any_hard_stop": True,
            "final_required_provider_state": "scaled_to_zero_and_verified",
        },
        "official_sources": [
            "https://huggingface.co/docs/inference-endpoints/pricing",
            "https://huggingface.co/docs/hub/en/billing",
        ],
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            issues.append(f"{key} mismatch")
    digest = value.get("authorization_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("authorization_sha256 must be a lowercase SHA-256")
    elif digest != authorization_sha256(value):
        issues.append("authorization_sha256 does not match canonical content")
    return issues


def _validate_main_carry_only_authorization(value: dict[str, Any]) -> list[str]:
    expanded_budget = value.get("authorization_id") in {
        "qwen-carry-only-l1-01-r02-a02-20260908-v1",
        "qwen-carry-only-l1-01-r02-a03-20260908-v1",
        "qwen-carry-only-l1-01-r03-20260909-v1",
        "qwen-carry-only-l1-02-r01-20260910-v1",
        "qwen-carry-only-l1-02-r02-gpt-20260911-v1",
        "qwen-carry-only-l1-02-r03-gpt-20260912-v1",
        "qwen-carry-only-l1-03-r01-gpt-20260913-v1",
        "qwen-carry-only-l1-03-r02-gpt-20260914-v1",
        "qwen-carry-only-l1-03-r02-gpt-a02-20260914-v1",
        "qwen-carry-only-l1-03-r03-gpt-20260914-v1",
        "qwen-carry-only-l2-01-r01-gpt-20260916-v1",
        "qwen-carry-only-l2-01-r02-gpt-20260917-v1",
        "qwen-carry-only-l2-01-r03-gpt-20260917-v1",
        "qwen-carry-only-l2-02-r01-gpt-20260919-v1",
        "qwen-carry-only-l2-02-r02-gpt-20260919-v1",
        "qwen-carry-only-l2-02-r03-gpt-20260920-v1",
        "qwen-carry-only-l2-03-r01-gpt-20260920-v1",
        "qwen-carry-only-l2-03-r02-gpt-20260921-v1",
        "qwen-carry-only-l2-03-r03-gpt-20260921-v1",
        "qwen-carry-only-l3-01-r01-gpt-20260922-v1",
        "qwen-carry-only-l3-01-r03-gpt-20260922-v1",
        "qwen-carry-only-l3-02-r02-gpt-20260923-v1",
        "qwen-carry-only-l3-02-r03-gpt-20260923-v1",
        "qwen-carry-only-l3-02-r01-gpt-20260923-v1",
        "qwen-carry-only-l3-01-r02-gpt-20260922-v1",
    }
    is_l201_r01 = value.get("authorization_id") == (
        "qwen-carry-only-l2-01-r01-gpt-20260916-v1"
    )
    is_l201_r02 = value.get("authorization_id") == (
        "qwen-carry-only-l2-01-r02-gpt-20260917-v1"
    )
    is_l201_r03 = value.get("authorization_id") == (
        "qwen-carry-only-l2-01-r03-gpt-20260917-v1"
    )
    is_l202_r01 = value.get("authorization_id") == (
        "qwen-carry-only-l2-02-r01-gpt-20260919-v1"
    )
    is_l202_r02 = value.get("authorization_id") == (
        "qwen-carry-only-l2-02-r02-gpt-20260919-v1"
    )
    is_l202_r03 = value.get("authorization_id") == (
        "qwen-carry-only-l2-02-r03-gpt-20260920-v1"
    )
    is_l203_r01 = value.get("authorization_id") == (
        "qwen-carry-only-l2-03-r01-gpt-20260920-v1"
    )
    is_l203_r02 = value.get("authorization_id") == (
        "qwen-carry-only-l2-03-r02-gpt-20260921-v1"
    )
    is_l203_r03 = value.get("authorization_id") == (
        "qwen-carry-only-l2-03-r03-gpt-20260921-v1"
    )
    is_l301_r02 = value.get("authorization_id") == "qwen-carry-only-l3-01-r02-gpt-20260922-v1"
    is_l302_r01 = value.get("authorization_id") == "qwen-carry-only-l3-02-r01-gpt-20260923-v1"
    is_l302_r02 = value.get("authorization_id") == "qwen-carry-only-l3-02-r02-gpt-20260923-v1"
    is_l302_r03 = value.get("authorization_id") == "qwen-carry-only-l3-02-r03-gpt-20260923-v1"
    is_l301_r03 = value.get("authorization_id") == "qwen-carry-only-l3-01-r03-gpt-20260922-v1"
    is_l301_r01 = value.get("authorization_id") == (
        "qwen-carry-only-l3-01-r01-gpt-20260922-v1"
    )
    is_l102_r02 = value.get("authorization_id") == (
        "qwen-carry-only-l1-02-r02-gpt-20260911-v1"
    )
    is_l102_r03 = value.get("authorization_id") == (
        "qwen-carry-only-l1-02-r03-gpt-20260912-v1"
    )
    is_l103_r01 = value.get("authorization_id") == (
        "qwen-carry-only-l1-03-r01-gpt-20260913-v1"
    )
    is_l103_r02 = value.get("authorization_id") == (
        "qwen-carry-only-l1-03-r02-gpt-20260914-v1"
    )
    is_l103_r02_a02 = value.get("authorization_id") == (
        "qwen-carry-only-l1-03-r02-gpt-a02-20260914-v1"
    )
    is_l103_r03 = value.get("authorization_id") == (
        "qwen-carry-only-l1-03-r03-gpt-20260914-v1"
    )
    is_l102 = value.get("authorization_id") in {
        "qwen-carry-only-l1-02-r01-20260910-v1",
        "qwen-carry-only-l1-02-r02-gpt-20260911-v1",
        "qwen-carry-only-l1-02-r03-gpt-20260912-v1",
    }
    is_r03 = (
        value.get("authorization_id")
        == "qwen-carry-only-l1-01-r03-20260909-v1"
    )
    is_a03 = (
        value.get("authorization_id")
        == "qwen-carry-only-l1-01-r02-a03-20260908-v1"
    )
    combined_budget = {
        "authorization_id": (
            "qwen-openai-main-l1-01-r02-a02-20260908-v1"
            if expanded_budget else "qwen-openai-main-l1-01-r01-20260901-v1"
        ),
        "currency": "USD", "hard_budget_usd": 5.0 if expanded_budget else 3.0,
        "operational_stop_threshold_usd": 4.2 if expanded_budget else 2.5,
        "reserve_usd": 0.8 if expanded_budget else 0.5,
        "qwen_hard_allocation_usd": 2.5, "qwen_operational_stop_usd": 2.1,
        "qwen_reserve_usd": 0.4,
        "openai_hard_allocation_usd": 2.5 if expanded_budget else 0.5,
        "openai_operational_stop_usd": 2.1 if expanded_budget else 0.4,
        "openai_reserve_usd": 0.4 if expanded_budget else 0.1,
        "combined_meter_must_aggregate_both_providers_before_each_next_paid_action": True,
        "automatic_reallocation_between_providers_prohibited": True,
        "reallocation_requires_user_feedback_and_reauthorization": True,
        "main_experiment_included": True,
    }
    if expanded_budget:
        combined_budget["supersedes_authorization_id"] = (
            "qwen-openai-main-l1-01-r01-20260901-v1"
        )
    expected = {
        "schema_version": "1.1.0",
        "status": "APPROVED_BUDGET_CARRY_ONLY",
        "authorization_id": value.get("authorization_id"),
        "authorized_on": "2026-09-23" if is_l302_r03 or is_l302_r02 or is_l302_r01 else "2026-09-22" if is_l301_r03 or is_l301_r02 or is_l301_r01 else "2026-09-21" if is_l203_r03 or is_l203_r02 else "2026-09-20" if is_l203_r01 or is_l202_r03 else "2026-09-19" if is_l202_r02 or is_l202_r01 else "2026-09-17" if is_l201_r03 or is_l201_r02 else "2026-09-16" if is_l201_r01 else "2026-09-14" if is_l103_r03 or is_l103_r02_a02 or is_l103_r02 else "2026-09-13" if is_l103_r01 else "2026-09-12" if is_l102_r03 else "2026-09-11" if is_l102_r02 else "2026-09-10" if is_l102 else "2026-09-09" if is_r03 else "2026-09-08",
        "timezone": "Australia/Sydney",
        "scope": {
            "provider": "hugging_face_inference_endpoints_dedicated",
            "included_phase": "budget_carry_only",
            "block_id": "L3-02-r03" if is_l302_r03 else "L3-02-r02" if is_l302_r02 else "L3-02-r01" if is_l302_r01 else "L3-01-r02" if is_l301_r02 else "L3-01-r03" if is_l301_r03 else "L3-01-r01" if is_l301_r01 else "L2-03-r03" if is_l203_r03 else "L2-03-r02" if is_l203_r02 else "L2-03-r01" if is_l203_r01 else "L2-02-r03" if is_l202_r03 else "L2-02-r02" if is_l202_r02 else "L2-02-r01" if is_l202_r01 else "L2-01-r03" if is_l201_r03 else "L2-01-r02" if is_l201_r02 else "L2-01-r01" if is_l201_r01 else "L1-03-r03" if is_l103_r03 else "L1-03-r02" if is_l103_r02_a02 or is_l103_r02 else "L1-03-r01" if is_l103_r01 else "L1-02-r03" if is_l102_r03 else "L1-02-r02" if is_l102_r02 else "L1-02-r01" if is_l102 else "L1-01-r03" if is_r03 else "L1-01-r02",
            "authorized_run_ids": [],
            "provider_calls_authorized": False,
            "main_experiment_included": False,
            "other_main_runs_included": False,
        },
        "combined_two_provider_budget": combined_budget,
        "authorization_boundaries": {
            "not_before": (
                "2026-09-23T10:50:24+10:00" if is_l302_r01 else "2026-09-23T13:34:24+10:00" if is_l302_r03 else "2026-09-23T11:18:38+10:00" if is_l302_r02 else "2026-09-22T18:44:49+10:00" if is_l301_r02
                else "2026-09-22T19:10:07+10:00" if is_l301_r03
                else "2026-09-22T16:09:30+10:00" if is_l301_r01
                else "2026-09-21T22:18:25+10:00" if is_l203_r03
                else "2026-09-21T16:33:51+10:00" if is_l203_r02
                else "2026-09-20T17:08:39+10:00" if is_l203_r01
                else "2026-09-20T11:10:25+10:00" if is_l202_r03
                else "2026-09-19T12:05:36+10:00" if is_l202_r02
                else "2026-09-19T11:22:10+10:00" if is_l202_r01
                else "2026-09-17T22:18:45+10:00" if is_l201_r03
                else "2026-09-17T11:00:07+10:00" if is_l201_r02
                else "2026-09-16T19:13:53+10:00" if is_l201_r01
                else "2026-09-14T22:55:16+10:00" if is_l103_r03
                else "2026-09-14T22:29:26+10:00" if is_l103_r02_a02
                else "2026-09-14T15:20:52+10:00" if is_l103_r02
                else "2026-09-13T19:35:43+10:00" if is_l103_r01
                else "2026-09-12T19:32:16+10:00" if is_l102_r03
                else "2026-09-11T10:57:10+10:00" if is_l102_r02
                else "2026-09-10T20:19:53+10:00" if is_l102
                else "2026-09-09T10:44:48+10:00" if is_r03
                else "2026-09-08T12:57:24+10:00" if is_a03
                else "2026-09-08T12:34:54+10:00" if expanded_budget
                else "2026-09-08T12:10:53+10:00"
            ),
            "provider_calls_prohibited": True,
            "budget_carry_forward_only": True,
            "credentials_must_not_be_loaded": True,
            "secrets_must_not_enter_evidence_or_configuration": True,
        },
        "cost_controls": {
            "currency": "USD",
            "hard_budget_usd": 2.5,
            "operational_stop_threshold_usd": 2.1,
            "reserve_usd": 0.4,
            "new_spend_authorized_usd": 0.0,
            "public_reference_hourly_rate_usd": 0.8,
        },
        "time_controls": {
            "maximum_cumulative_endpoint_running_seconds": 9450,
        },
        "failure_policy": {
            "any_qwen_provider_action_is_a_hard_stop": True,
            "reauthorization_required_before_any_qwen_provider_call": True,
            "final_required_provider_state": "scaled_to_zero_and_verified",
        },
        "authorization_sha256": value.get("authorization_sha256"),
    }
    if set(value) != set(expected):
        return [f"top-level fields must equal {sorted(expected)}"]
    issues = [
        f"{key} mismatch"
        for key, wanted in expected.items()
        if key != "authorization_sha256" and value.get(key) != wanted
    ]
    digest = value.get("authorization_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append("authorization_sha256 must be a lowercase SHA-256")
    elif digest != authorization_sha256(value):
        issues.append("authorization_sha256 does not match canonical content")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Qwen paid-stage authorization")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "qwen_paid_stage_authorization.json",
    )
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_qwen_paid_stage_authorization(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")
    print(f"authorization_sha256={authorization_sha256(value)}")


if __name__ == "__main__":
    main()
