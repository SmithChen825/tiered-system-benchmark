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


def validate_openai_paid_stage_authorization(value: dict[str, Any]) -> list[str]:
    if value.get("authorization_id") in {
        "openai-main-l1-01-r01-20260901-v1",
        "openai-main-l1-01-r02-20260908-v1",
        "openai-main-l1-01-r02-a02-20260908-v1",
        "openai-main-l1-01-r02-a03-20260908-v1",
        "openai-main-l1-01-r03-20260909-v1",
        "openai-main-l1-02-r01-20260910-v1",
        "openai-main-l1-02-r02-20260911-v1",
        "openai-main-l1-02-r03-20260912-v1",
        "openai-main-l1-03-r01-20260913-v1",
        "openai-main-l1-03-r02-20260914-v1",
        "openai-main-l1-03-r02-a02-20260914-v1",
        "openai-main-l1-03-r03-20260914-v1",
        "openai-main-l2-01-r01-20260916-v1",
        "openai-main-l2-01-r02-20260917-v1",
        "openai-main-l2-01-r03-20260917-v1",
        "openai-main-l2-02-r01-20260919-v1",
        "openai-main-l2-02-r02-20260919-v1",
        "openai-main-l2-02-r03-20260920-v1",
        "openai-main-l2-03-r01-20260920-v1",
        "openai-main-l2-03-r02-20260921-v1",
        "openai-main-l2-03-r03-20260921-v1",
        "openai-main-l3-01-r01-20260922-v1",
        "openai-main-l3-01-r03-20260922-v1",
        "openai-main-l3-02-r02-20260923-v1",
        "openai-main-l3-02-r03-20260923-v1",
        "openai-main-l3-02-r01-20260923-v1",
        "openai-main-l3-01-r02-20260922-v1",
    }:
        return _validate_main_authorization(value)
    if value.get("authorization_id") in {
        "openai-carry-only-l1-01-r02-20260907-v1",
        "openai-carry-only-l1-01-r03-20260909-v1",
        "openai-carry-only-l1-02-r01-20260910-v1",
        "openai-carry-only-l1-02-r02-20260911-v1",
        "openai-carry-only-l1-02-r03-20260912-v1",
        "openai-carry-only-l1-03-r01-20260912-v1",
        "openai-carry-only-l1-03-r02-20260914-v1",
        "openai-carry-only-l1-03-r03-20260916-v1",
        "openai-carry-only-l2-01-r01-20260916-v1",
        "openai-carry-only-l2-01-r02-20260917-v1",
        "openai-carry-only-l2-01-r03-20260917-v1",
        "openai-carry-only-l2-02-r01-qwen-20260919-v1",
        "openai-carry-only-l2-02-r02-qwen-20260919-v1",
        "openai-carry-only-l2-02-r03-qwen-20260920-v1",
        "openai-carry-only-l2-03-r01-qwen-20260920-v1",
        "openai-carry-only-l2-03-r02-qwen-20260921-v1",
        "openai-carry-only-l2-03-r03-qwen-20260921-v1",
        "openai-carry-only-l3-01-r01-qwen-20260922-v1",
        "openai-carry-only-l3-01-r03-qwen-20260922-v1",
        "openai-carry-only-l3-02-r03-qwen-20260923-v1",
        "openai-carry-only-l3-02-r02-qwen-20260923-v1",
        "openai-carry-only-l3-02-r01-qwen-20260923-v1",
        "openai-carry-only-l3-01-r02-qwen-20260922-v1",
    }:
        return _validate_main_carry_only_authorization(value)
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
        "request_controls",
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
    if value["authorization_id"] != "openai-gpt-5-4-smoke-pilot-cost-20260811-v2":
        issues.append("authorization_id mismatch")
    if value["authorized_on"] != "2026-08-11":
        issues.append("authorized_on mismatch")
    if value["timezone"] != "Australia/Sydney":
        issues.append("timezone mismatch")

    if value["scope"] != {
        "provider": "openai_api",
        "endpoint": "https://api.openai.com/v1/responses",
        "model_snapshot": "gpt-5.4-2026-03-05",
        "included_phases": ["live_smoke", "openai_four_task_pilot"],
        "pilot_task_ids": EXPECTED_TASKS,
        "pilot_run_count": 4,
        "main_experiment_included": False,
    }:
        issues.append("scope must remain limited to GPT-5.4 smoke and four pilot runs")

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
        "non_benchmark_smoke_may_precede_complete_experiment_freeze": True,
        "benchmark_task_calls_require_complete_frozen_experiment_manifest": True,
        "dedicated_openai_project_required": True,
        "dedicated_project_tracked_monthly_spend_must_start_at_usd": 0.0,
        "runtime_paid_stage_meter_must_be_bound_before_first_call": True,
        "credentials_must_be_runtime_only": True,
        "secrets_must_not_enter_evidence_or_configuration": True,
        "standard_processing_only": True,
        "regional_priority_fast_flex_batch_processing_prohibited": True,
    }:
        issues.append("authorization boundaries mismatch")

    cost = value["cost_controls"]
    expected_cost = {
        "currency": "USD",
        "hard_budget_usd": 8.0,
        "operational_stop_threshold_usd": 7.0,
        "reserve_for_in_flight_requests_and_enforcement_lag_usd": 1.0,
        "provider_project_hard_spend_limit_required": True,
        "provider_project_hard_spend_limit_usd": 8.0,
        "provider_project_spend_alert_usd": 5.0,
        "provider_hard_limit_enforcement_is_not_instantaneous": True,
        "final_recorded_spend_may_slightly_exceed_provider_hard_limit": True,
        "pricing_checked_on": "2026-08-11",
        "provider_billing_basis": "per_token_at_selected_model_rates",
        "standard_short_context_usd_per_million_tokens": {
            "uncached_input": 2.5,
            "cached_input": 0.25,
            "output": 15.0,
        },
        "maximum_output_tokens_per_response": 4096,
        "account_visible_pricing_and_zero_project_baseline_must_be_captured_before_first_call": True,
        "local_cumulative_token_cost_estimate_required_before_each_next_call": True,
        "cost_estimate_rule": "maximum_of_dedicated_project_account_visible_incremental_cost_and_cumulative_response_usage_priced_at_the_captured_applicable_rates",
        "maximum_concurrent_paid_requests": 1,
        "maximum_concurrent_pilot_runs": 1,
        "built_in_paid_tools_and_additional_paid_resources_prohibited": True,
        "stop_at_earliest_cost_request_or_time_limit": True,
    }
    if cost != expected_cost:
        issues.append("cost controls must preserve OpenAI's USD 8 project cap and USD 7 stop")
    elif (
        cost["operational_stop_threshold_usd"]
        + cost["reserve_for_in_flight_requests_and_enforcement_lag_usd"]
        != cost["hard_budget_usd"]
    ):
        issues.append("operational threshold plus reserve must equal the hard budget")
    elif cost["provider_project_hard_spend_limit_usd"] != cost["hard_budget_usd"]:
        issues.append("provider project hard limit must equal the user hard budget")

    requests = value["request_controls"]
    expected_requests = {
        "live_smoke_maximum_logical_requests": 2,
        "maximum_successful_model_responses_per_pilot_task": 20,
        "maximum_successful_model_responses_across_four_pilot_tasks": 80,
        "maximum_http_attempts_per_logical_request": 3,
        "maximum_http_attempts_per_pilot_task": 60,
        "maximum_http_attempts_across_four_pilot_tasks": 240,
        "pilot_api_action_limit_per_task": 15,
        "request_count_limit_is_a_paid_stage_safety_stop_not_a_success_outcome": True,
        "stop_and_request_feedback_when_limit_reached": True,
    }
    if requests != expected_requests:
        issues.append("request controls mismatch")
    else:
        if requests["maximum_successful_model_responses_per_pilot_task"] * 4 != requests["maximum_successful_model_responses_across_four_pilot_tasks"]:
            issues.append("successful-response per-task and four-task limits disagree")
        if requests["maximum_successful_model_responses_per_pilot_task"] * requests["maximum_http_attempts_per_logical_request"] != requests["maximum_http_attempts_per_pilot_task"]:
            issues.append("per-task response and HTTP-attempt limits disagree")
        if requests["maximum_http_attempts_per_pilot_task"] * 4 != requests["maximum_http_attempts_across_four_pilot_tasks"]:
            issues.append("per-task and four-task HTTP-attempt limits disagree")

    time_controls = value["time_controls"]
    expected_time = {
        "pilot_task_limit_seconds": 5400,
        "openai_pilot_task_count": 4,
        "maximum_timed_pilot_task_seconds": 21600,
        "maximum_live_smoke_operator_seconds": 3600,
        "maximum_total_stage_operator_seconds": 28800,
        "stop_and_request_feedback_when_limit_reached": True,
    }
    if time_controls != expected_time:
        issues.append("time controls mismatch")
    elif time_controls["pilot_task_limit_seconds"] * time_controls["openai_pilot_task_count"] != time_controls["maximum_timed_pilot_task_seconds"]:
        issues.append("timed pilot ceiling must equal four task limits")

    if value["failure_policy"] != {
        "stop_on_first_failed_or_unavailable_live_smoke_gate": True,
        "stop_on_authentication_permission_model_tool_calling_schema_pricing_or_spend_limit_failure": True,
        "automatic_model_endpoint_service_tier_context_limit_or_transport_substitution_prohibited": True,
        "candidate_amendment_and_user_feedback_required_before_retry_with_changed_configuration": True,
        "pilot_runs_prohibited_until_live_smoke_passes_and_the_pilot_manifest_is_frozen": True,
        "main_experiment_requires_separate_cost_estimate_and_authorization": True,
    }:
        issues.append("failure policy must remain fail closed")

    if value["official_sources"] != [
        "https://developers.openai.com/api/docs/pricing",
        "https://developers.openai.com/api/docs/guides/spend-limits",
        "https://developers.openai.com/api/docs/models/gpt-5.4",
    ]:
        issues.append("official OpenAI sources mismatch")

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
        "authorization_boundaries", "cost_controls", "request_controls",
        "time_controls", "failure_policy", "official_sources",
        "authorization_sha256",
    }
    if set(value) != expected_top:
        return [f"top-level fields must equal {sorted(expected_top)}"]
    variants = {
        "openai-main-l1-01-r01-20260901-v1": {
            "authorized_on": "2026-09-01",
            "not_before": "2026-09-01T12:36:02+10:00",
            "block_id": "L1-01-r01",
            "run_id": "main-L1-01-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-01",
        },
        "openai-main-l1-01-r02-20260908-v1": {
            "authorized_on": "2026-09-08",
            "not_before": "2026-09-08T12:10:53+10:00",
            "block_id": "L1-01-r02",
            "run_id": "main-L1-01-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-08",
        },
        "openai-main-l1-01-r02-a02-20260908-v1": {
            "authorized_on": "2026-09-08",
            "not_before": "2026-09-08T12:34:54+10:00",
            "block_id": "L1-01-r02",
            "run_id": "main-L1-01-gpt-5-4-r02-a02",
            "pricing_checked_on": "2026-09-08",
            "expanded_budget": True,
        },
        "openai-main-l1-01-r02-a03-20260908-v1": {
            "authorized_on": "2026-09-08",
            "not_before": "2026-09-08T12:57:24+10:00",
            "block_id": "L1-01-r02",
            "run_id": "main-L1-01-gpt-5-4-r02-a03",
            "pricing_checked_on": "2026-09-08",
            "expanded_budget": True,
        },
        "openai-main-l1-01-r03-20260909-v1": {
            "authorized_on": "2026-09-09",
            "not_before": "2026-09-09T10:44:48+10:00",
            "block_id": "L1-01-r03",
            "run_id": "main-L1-01-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-08",
            "expanded_budget": True,
        },
        "openai-main-l1-02-r01-20260910-v1": {
            "authorized_on": "2026-09-10",
            "not_before": "2026-09-10T20:19:53+10:00",
            "block_id": "L1-02-r01",
            "run_id": "main-L1-02-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-08",
            "expanded_budget": True,
        },
        "openai-main-l1-02-r02-20260911-v1": {
            "authorized_on": "2026-09-11",
            "not_before": "2026-09-11T10:57:10+10:00",
            "block_id": "L1-02-r02",
            "run_id": "main-L1-02-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-08",
            "expanded_budget": True,
        },
        "openai-main-l1-02-r03-20260912-v1": {
            "authorized_on": "2026-09-12",
            "not_before": "2026-09-12T19:32:16+10:00",
            "block_id": "L1-02-r03",
            "run_id": "main-L1-02-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-12",
            "expanded_budget": True,
        },
        "openai-main-l1-03-r01-20260913-v1": {
            "authorized_on": "2026-09-13",
            "not_before": "2026-09-13T19:35:43+10:00",
            "block_id": "L1-03-r01",
            "run_id": "main-L1-03-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-13",
            "expanded_budget": True,
        },
        "openai-main-l1-03-r02-20260914-v1": {
            "authorized_on": "2026-09-14",
            "not_before": "2026-09-14T15:20:52+10:00",
            "block_id": "L1-03-r02",
            "run_id": "main-L1-03-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-14",
            "expanded_budget": True,
        },
        "openai-main-l1-03-r02-a02-20260914-v1": {
            "authorized_on": "2026-09-14",
            "not_before": "2026-09-14T22:29:26+10:00",
            "block_id": "L1-03-r02",
            "run_id": "main-L1-03-gpt-5-4-r02-a02",
            "pricing_checked_on": "2026-09-14",
            "expanded_budget": True,
        },
        "openai-main-l1-03-r03-20260914-v1": {
            "authorized_on": "2026-09-14",
            "not_before": "2026-09-14T22:55:16+10:00",
            "block_id": "L1-03-r03",
            "run_id": "main-L1-03-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-14",
            "expanded_budget": True,
        },
        "openai-main-l2-01-r01-20260916-v1": {
            "authorized_on": "2026-09-16",
            "not_before": "2026-09-16T19:13:53+10:00",
            "block_id": "L2-01-r01",
            "run_id": "main-L2-01-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-16",
            "expanded_budget": True,
        },
        "openai-main-l2-01-r02-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T11:00:07+10:00",
            "block_id": "L2-01-r02",
            "run_id": "main-L2-01-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-17",
            "expanded_budget": True,
        },
        "openai-main-l2-01-r03-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T22:18:45+10:00",
            "block_id": "L2-01-r03",
            "run_id": "main-L2-01-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-17",
            "expanded_budget": True,
        },
        "openai-main-l2-02-r01-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T11:22:10+10:00",
            "block_id": "L2-02-r01",
            "run_id": "main-L2-02-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-19",
            "expanded_budget": True,
        },
        "openai-main-l2-02-r02-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T12:05:36+10:00",
            "block_id": "L2-02-r02",
            "run_id": "main-L2-02-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-19",
            "expanded_budget": True,
        },
        "openai-main-l2-02-r03-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T11:10:25+10:00",
            "block_id": "L2-02-r03",
            "run_id": "main-L2-02-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-20",
            "expanded_budget": True,
        },
        "openai-main-l2-03-r01-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T17:08:39+10:00",
            "block_id": "L2-03-r01",
            "run_id": "main-L2-03-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-20",
            "expanded_budget": True,
        },
        "openai-main-l2-03-r02-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T16:33:51+10:00",
            "block_id": "L2-03-r02",
            "run_id": "main-L2-03-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-21",
            "expanded_budget": True,
        },
        "openai-main-l2-03-r03-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T22:18:25+10:00",
            "block_id": "L2-03-r03",
            "run_id": "main-L2-03-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-21",
            "expanded_budget": True,
        },
        "openai-main-l3-01-r01-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T16:09:30+10:00",
            "block_id": "L3-01-r01",
            "run_id": "main-L3-01-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
        "openai-main-l3-01-r03-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T19:10:07+10:00",
            "block_id": "L3-01-r03",
            "run_id": "main-L3-01-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
        "openai-main-l3-02-r02-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T11:18:38+10:00",
            "block_id": "L3-02-r02",
            "run_id": "main-L3-02-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
        "openai-main-l3-02-r03-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T13:34:24+10:00",
            "block_id": "L3-02-r03",
            "run_id": "main-L3-02-gpt-5-4-r03-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
        "openai-main-l3-02-r01-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T10:50:24+10:00",
            "block_id": "L3-02-r01",
            "run_id": "main-L3-02-gpt-5-4-r01-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
        "openai-main-l3-01-r02-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T18:44:49+10:00",
            "block_id": "L3-01-r02",
            "run_id": "main-L3-01-gpt-5-4-r02-a01",
            "pricing_checked_on": "2026-09-22",
            "expanded_budget": True,
        },
    }
    variant = variants.get(value.get("authorization_id"))
    if variant is None:
        return ["unsupported main authorization_id"]
    expanded_budget = variant.get("expanded_budget", False)
    combined_budget = {
        "authorization_id": (
            "qwen-openai-main-l1-01-r02-a02-20260908-v1"
            if expanded_budget else "qwen-openai-main-l1-01-r01-20260901-v1"
        ),
        "currency": "USD", "hard_budget_usd": 5.0 if expanded_budget else 3.0,
        "operational_stop_threshold_usd": 4.2 if expanded_budget else 2.5,
        "reserve_usd": 0.8 if expanded_budget else 0.5,
        "qwen_hard_allocation_usd": 2.5, "qwen_operational_stop_usd": 2.1,
        "qwen_reserve_usd": 0.4, "openai_hard_allocation_usd": 2.5 if expanded_budget else 0.5,
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
        "authorized_on": variant["authorized_on"],
        "timezone": "Australia/Sydney",
        "scope": {
            "provider": "openai_api",
            "endpoint": "https://api.openai.com/v1/responses",
            "model_snapshot": "gpt-5.4-2026-03-05",
            "included_phase": "main",
            "block_id": variant["block_id"],
            "authorized_run_ids": [variant["run_id"]],
            "main_experiment_included": True,
            "other_main_runs_included": False,
        },
        "combined_two_provider_budget": combined_budget,
        "authorization_boundaries": {
            "not_before": variant["not_before"],
            "benchmark_task_calls_require_complete_frozen_main_manifest": True,
            "fresh_main_ledger_required": True,
            "account_visible_starting_balance_evidence_required_before_first_call": True,
            "credentials_must_be_runtime_only": True,
            "secrets_must_not_enter_evidence_or_configuration": True,
            "standard_processing_only": True,
        },
        "cost_controls": {
            "currency": "USD", "hard_budget_usd": 2.5 if expanded_budget else 0.5,
            "operational_stop_threshold_usd": 2.1 if expanded_budget else 0.4,
            "reserve_for_in_flight_requests_and_enforcement_lag_usd": 0.4 if expanded_budget else 0.1,
            "provider_project_hard_spend_limit_required": True,
            "provider_project_hard_spend_limit_usd": 2.5 if expanded_budget else 0.5,
            "pricing_checked_on": variant["pricing_checked_on"],
            "provider_billing_basis": "per_token_at_selected_model_rates",
            "standard_short_context_usd_per_million_tokens": {
                "uncached_input": 2.5, "cached_input": 0.25, "output": 15.0,
            },
            "maximum_output_tokens_per_response": 4096,
            "maximum_concurrent_paid_requests": 1,
            "built_in_paid_tools_and_additional_paid_resources_prohibited": True,
            "stop_at_earliest_cost_request_or_time_limit": True,
        },
        "request_controls": {
            "maximum_successful_model_responses_for_authorized_run": 35,
            "maximum_http_attempts_per_logical_request": 3,
            "maximum_http_attempts_for_authorized_run": 105,
            "main_api_action_limit": 30,
            "stop_and_request_feedback_when_limit_reached": True,
        },
        "time_controls": {
            "main_task_limit_seconds": 5400,
            "authorized_run_count": 1,
            "maximum_timed_task_seconds": 5400,
            "stop_and_request_feedback_when_limit_reached": True,
        },
        "failure_policy": {
            "stop_on_authentication_permission_model_tool_calling_schema_pricing_or_spend_limit_failure": True,
            "automatic_model_endpoint_service_tier_context_limit_or_transport_substitution_prohibited": True,
            "candidate_amendment_and_user_feedback_required_before_retry_with_changed_configuration": True,
            "authorization_expires_after_the_listed_run_or_any_hard_stop": True,
        },
        "official_sources": [
            "https://developers.openai.com/api/docs/pricing",
            "https://developers.openai.com/api/docs/guides/spend-limits",
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
    variants = {
        "openai-carry-only-l1-01-r02-20260907-v1": {
            "authorized_on": "2026-09-07",
            "not_before": "2026-09-07T13:57:43+10:00",
            "block_id": "L1-01-r02",
            "expanded_budget": False,
        },
        "openai-carry-only-l1-01-r03-20260909-v1": {
            "authorized_on": "2026-09-09",
            "not_before": "2026-09-09T12:00:15+10:00",
            "block_id": "L1-01-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-02-r01-20260910-v1": {
            "authorized_on": "2026-09-10",
            "not_before": "2026-09-10T15:01:59+10:00",
            "block_id": "L1-02-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-02-r02-20260911-v1": {
            "authorized_on": "2026-09-11",
            "not_before": "2026-09-11T10:18:06+10:00",
            "block_id": "L1-02-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-02-r03-20260912-v1": {
            "authorized_on": "2026-09-12",
            "not_before": "2026-09-12T10:53:45+10:00",
            "block_id": "L1-02-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-03-r01-20260912-v1": {
            "authorized_on": "2026-09-12",
            "not_before": "2026-09-12T21:04:53+10:00",
            "block_id": "L1-03-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-03-r02-20260914-v1": {
            "authorized_on": "2026-09-14",
            "not_before": "2026-09-14T10:03:00+10:00",
            "block_id": "L1-03-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l1-03-r03-20260916-v1": {
            "authorized_on": "2026-09-16",
            "not_before": "2026-09-16T16:35:04+10:00",
            "block_id": "L1-03-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-01-r01-20260916-v1": {
            "authorized_on": "2026-09-16",
            "not_before": "2026-09-16T19:55:41+10:00",
            "block_id": "L2-01-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-01-r02-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T13:02:00+10:00",
            "block_id": "L2-01-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-01-r03-20260917-v1": {
            "authorized_on": "2026-09-17",
            "not_before": "2026-09-17T23:00:00+10:00",
            "block_id": "L2-01-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-02-r01-qwen-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T11:35:49+10:00",
            "block_id": "L2-02-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-02-r02-qwen-20260919-v1": {
            "authorized_on": "2026-09-19",
            "not_before": "2026-09-19T15:04:38+10:00",
            "block_id": "L2-02-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-02-r03-qwen-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T14:08:05+10:00",
            "block_id": "L2-02-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-03-r01-qwen-20260920-v1": {
            "authorized_on": "2026-09-20",
            "not_before": "2026-09-20T23:59:49+10:00",
            "block_id": "L2-03-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-03-r02-qwen-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T16:07:15+10:00",
            "block_id": "L2-03-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l2-03-r03-qwen-20260921-v1": {
            "authorized_on": "2026-09-21",
            "not_before": "2026-09-21T22:53:25+10:00",
            "block_id": "L2-03-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-01-r01-qwen-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T17:16:29+10:00",
            "block_id": "L3-01-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-01-r03-qwen-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T21:40:22+10:00",
            "block_id": "L3-01-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-02-r03-qwen-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T13:10:13+10:00",
            "block_id": "L3-02-r03",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-02-r02-qwen-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T11:12:46+10:00",
            "block_id": "L3-02-r02",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-02-r01-qwen-20260923-v1": {
            "authorized_on": "2026-09-23",
            "not_before": "2026-09-23T10:32:30+10:00",
            "block_id": "L3-02-r01",
            "expanded_budget": True,
        },
        "openai-carry-only-l3-01-r02-qwen-20260922-v1": {
            "authorized_on": "2026-09-22",
            "not_before": "2026-09-22T18:55:11+10:00",
            "block_id": "L3-01-r02",
            "expanded_budget": True,
        },
    }
    variant = variants.get(value.get("authorization_id"))
    if variant is None:
        return ["unsupported main carry-only authorization_id"]
    expanded_budget = variant["expanded_budget"] is True
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
        "authorized_on": variant["authorized_on"],
        "timezone": "Australia/Sydney",
        "scope": {
            "provider": "openai_api",
            "included_phase": "budget_carry_only",
            "block_id": variant["block_id"],
            "authorized_run_ids": [],
            "provider_calls_authorized": False,
            "main_experiment_included": False,
            "other_main_runs_included": False,
        },
        "combined_two_provider_budget": combined_budget,
        "authorization_boundaries": {
            "not_before": variant["not_before"],
            "provider_calls_prohibited": True,
            "budget_carry_forward_only": True,
            "credentials_must_not_be_loaded": True,
            "secrets_must_not_enter_evidence_or_configuration": True,
        },
        "cost_controls": {
            "currency": "USD",
            "hard_budget_usd": 2.5 if expanded_budget else 0.5,
            "operational_stop_threshold_usd": 2.1 if expanded_budget else 0.4,
            "reserve_usd": 0.4 if expanded_budget else 0.1,
            "new_spend_authorized_usd": 0.0,
        },
        "failure_policy": {
            "any_openai_provider_action_is_a_hard_stop": True,
            "reauthorization_required_before_any_openai_provider_call": True,
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
    parser = argparse.ArgumentParser(description="Validate the OpenAI paid-stage authorization")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "openai_paid_stage_authorization.json",
    )
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_openai_paid_stage_authorization(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")
    print(f"authorization_sha256={authorization_sha256(value)}")


if __name__ == "__main__":
    main()
