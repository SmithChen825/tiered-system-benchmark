from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT  # type: ignore


EXPECTED_PLAN = {
    "schema_version": "1.0.0",
    "status": "FROZEN",
    "freeze_scope": "pilot_candidate",
    "analysis_plan_id": "tsb-pilot-operational-analysis-v1",
    "applies_to": {
        "phase": "pilot",
        "scheduled_runs": 16,
        "tasks": 4,
        "systems": 4,
        "repetitions_per_task": 1,
        "excluded_from_main_experiment_dataset": True,
        "inferential_system_comparison_permitted": False,
    },
    "objectives": [
        "validate_task_wall_clock_suitability",
        "validate_api_action_and_command_timeout_suitability",
        "validate_evidence_completeness_and_finalization",
        "validate_live_provider_and_tool_call_compatibility",
        "estimate_main_experiment_time_and_provider_cost",
    ],
    "summaries": {
        "run_accounting": [
            "scheduled",
            "valid_successful",
            "valid_unsuccessful",
            "invalidated_and_rerun",
        ],
        "elapsed_time": [
            "per_run_seconds",
            "median_by_system",
            "range_by_system",
            "limit_event_count",
        ],
        "api_limits": [
            "observable_actions_per_api_run",
            "action_limit_event_count",
            "command_timeout_event_count",
        ],
        "evidence": [
            "required_file_completeness_per_run",
            "validator_pass_or_fail",
            "redaction_check_pass_or_fail",
        ],
        "provider_cost": [
            "provider_reported_or_account_visible_cost_usd",
            "conservative_estimated_cost_usd",
            "endpoint_running_minutes",
        ],
        "success_outcome_role": "diagnostic_only_not_a_system_ranking",
    },
    "decision_process": {
        "task_wall_clock_start_seconds": 5400,
        "api_action_limit_start": 15,
        "command_timeout_start_seconds": 180,
        "maximum_pre_main_adjustments_per_limit": 1,
        "adjustment_requires_trace_evidence_and_written_rationale": True,
        "adjustment_must_be_fixed_before_main_experiment": True,
        "no_automatic_threshold_optimization_from_success_outcomes": True,
        "unchanged_values_must_also_receive_a_written_review_decision": True,
    },
    "exclusions": [
        "pilot_runs_from_144_run_main_dataset",
        "wilson_or_bootstrap_inference_on_pilot_success",
        "pairwise_p_values_or_holm_adjustment_on_pilot_results",
        "cross_interface_action_count_comparison",
        "weighted_aggregate_scoring",
        "private_reasoning_inference",
        "task_or_evaluator_tuning_to_favor_an_observed_system",
    ],
    "evidence_requirements": {
        "one_row_per_scheduled_pilot_slot": True,
        "invalidated_attempts_retained": True,
        "first_valid_terminal_attempt_used_for_operational_summary": True,
        "raw_evidence_links_required": True,
        "configuration_and_input_hashes_required": True,
        "decision_record_required_before_main_freeze": True,
    },
    "reproducibility": {
        "timezone": "Australia/Sydney",
        "summary_implementation": "python_standard_library_or_frozen_equivalent",
        "external_statistical_packages_required": False,
        "input_dataset_sha256_required": True,
        "analysis_script_sha256_required": True,
    },
    "pending_decisions": [],
    "notes": [
        "This plan evaluates whether the experiment procedure is executable and adequately bounded; it does not estimate comparative system performance.",
        "The main-experiment analysis remains separately defined in analysis_plan.candidate.json and is not silently frozen by this pilot plan.",
    ],
}


def validate_pilot_analysis_plan(
    value: dict[str, Any], *, require_frozen: bool = True
) -> list[str]:
    issues: list[str] = []
    if value != EXPECTED_PLAN:
        issues.append("pilot analysis plan does not match the frozen operational contract")
    if require_frozen and value.get("status") != "FROZEN":
        issues.append("pilot analysis plan must be FROZEN before pilot execution")
    applies_to = value.get("applies_to", {})
    if applies_to.get("excluded_from_main_experiment_dataset") is not True:
        issues.append("pilot runs must remain excluded from the main dataset")
    if applies_to.get("inferential_system_comparison_permitted") is not False:
        issues.append("pilot inferential system comparison must remain prohibited")
    if value.get("pending_decisions") != []:
        issues.append("pilot operational analysis cannot contain pending decisions")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen pilot operational analysis plan")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "pilot_analysis_plan.json",
    )
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_pilot_analysis_plan(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")


if __name__ == "__main__":
    main()
