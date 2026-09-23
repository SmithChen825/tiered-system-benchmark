from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .api_wrapper.core import WrapperSettings
from .common import REPOSITORY_ROOT
from .create_run import (
    PILOT_API_ACTION_LIMIT,
    PILOT_COMMAND_TIMEOUT_SECONDS,
    PILOT_CONSECUTIVE_NO_ACTION_RESPONSE_LIMIT,
)


SCHEMA_VERSION = "1.0.0"
FREEZE_SCOPES = {"pilot_candidate", "main_experiment"}
API_SYSTEMS = ["gpt-5.4", "qwen2.5-coder-7b-instruct"]
ALL_SYSTEMS = ["cursor", "devin", "gpt-5.4", "qwen2.5-coder-7b-instruct"]
CONTEXT_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "applies_to",
    "limit",
    "measurement",
    "immutable_prefix",
    "turn_group",
    "pruning",
    "internal_safety_guard",
    "pending_decisions",
    "notes",
}
EXECUTION_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "common_task_wall_clock",
    "api_wrapper_limits",
    "pre_freeze_adjustment",
    "limit_event_outcome",
    "pending_decisions",
    "notes",
}
EXPECTED_CONTEXT_APPLIES_TO = {
    "evaluation_interface": "api_wrapper",
    "systems": API_SYSTEMS,
    "identical_policy_required": True,
}
EXPECTED_MEASUREMENT = {
    "unit": "python_unicode_code_points",
    "included": "ContextMessage.content for retained messages",
    "excluded": "structured tool-call names, IDs, and argument objects",
    "threshold_kind": "retention_threshold_not_hard_provider_payload_cap",
}
EXPECTED_IMMUTABLE_PREFIX = {
    "messages": ["system_prompt", "task_prompt"],
    "never_dropped": True,
}
EXPECTED_TURN_GROUP = {
    "definition": (
        "one assistant message plus all linked tool-result messages from that model turn"
    ),
    "partial_group_allowed": False,
}
EXPECTED_PRUNING = {
    "enabled_when": "max_context_characters_is_not_null",
    "drop_order": "oldest_complete_turn_first",
    "minimum_retained_turn_groups": 1,
    "check_timing": "after_assistant_or_tool_result_append",
    "context_notice_position": "after_system_prompt_before_task_prompt",
    "context_notice_template": (
        "[CONTEXT_NOTICE] {dropped_turns} older complete model turn(s) were "
        "removed by the frozen context limit."
    ),
    "may_exceed_threshold_to_preserve_prefix_and_latest_turn": True,
}
EXPECTED_LIMIT_OUTCOME = {
    "validity": "valid_unsuccessful_outcome",
    "further_agent_actions": "stopped",
    "final_state_evaluation": "still_runs",
}
EXPECTED_ADJUSTMENT_POLICY = {
    "maximum_total_adjustments": 1,
    "eligible_limits": ["api_action_limit", "command_timeout_seconds"],
    "requires_pilot_evidence": True,
    "must_be_documented_before_main_freeze": True,
    "post_freeze_change_requires_amendment": True,
}
EXPECTED_CANDIDATE_CONTEXT_PENDING = ["max_context_characters"]
EXPECTED_CANDIDATE_EXECUTION_PENDING = [
    "task_wall_clock_seconds",
    "final_api_action_limit",
    "final_command_timeout_seconds",
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_top_fields(
    value: dict[str, Any], expected: set[str], label: str
) -> tuple[list[str], bool]:
    issues: list[str] = []
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing:
        issues.append(f"Missing {label} fields: " + ", ".join(missing))
    if unexpected:
        issues.append(f"Unexpected {label} fields: " + ", ".join(unexpected))
    return issues, not missing


def _validate_common_status(
    value: dict[str, Any], *, require_frozen: bool, issues: list[str]
) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    status = value.get("status")
    if status not in {"CANDIDATE", "FROZEN"}:
        issues.append("status must be CANDIDATE or FROZEN")
    if require_frozen and status != "FROZEN":
        issues.append("status must be FROZEN before experiment execution")
    scope = value.get("freeze_scope")
    if status == "CANDIDATE" and scope is not None:
        issues.append("freeze_scope must be null while CANDIDATE")
    if status == "FROZEN" and scope not in FREEZE_SCOPES:
        issues.append(f"freeze_scope must be one of {sorted(FREEZE_SCOPES)} when frozen")


def _validate_notes(value: Any, label: str, issues: list[str]) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        issues.append(f"{label} must be a list of non-empty strings")


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_context_policy(
    value: dict[str, Any], *, require_frozen: bool = False
) -> list[str]:
    issues, complete = _check_top_fields(value, CONTEXT_FIELDS, "context-policy")
    if not complete:
        return issues
    _validate_common_status(value, require_frozen=require_frozen, issues=issues)
    if value["applies_to"] != EXPECTED_CONTEXT_APPLIES_TO:
        issues.append("applies_to must bind the identical policy to both API systems")
    limit = value["limit"]
    if not isinstance(limit, dict) or set(limit) != {
        "max_context_characters",
        "selection_status",
        "must_be_positive_when_selected",
        "must_be_frozen_before_pilot",
    }:
        issues.append("limit has unexpected structure")
    else:
        if limit["must_be_positive_when_selected"] is not True:
            issues.append("limit.must_be_positive_when_selected must be true")
        if limit["must_be_frozen_before_pilot"] is not True:
            issues.append("limit.must_be_frozen_before_pilot must be true")
        if value["status"] == "CANDIDATE":
            if limit["max_context_characters"] is not None:
                issues.append("candidate max_context_characters must remain null")
            if limit["selection_status"] != "pending_pre_pilot_review":
                issues.append("candidate context selection_status must remain pending")
        elif value["status"] == "FROZEN":
            if not _positive_integer(limit["max_context_characters"]):
                issues.append("frozen max_context_characters must be a positive integer")
            if limit["selection_status"] != "selected_and_frozen":
                issues.append("frozen context selection_status must be selected_and_frozen")
    if value["measurement"] != EXPECTED_MEASUREMENT:
        issues.append("measurement does not match ConversationContext character accounting")
    if value["immutable_prefix"] != EXPECTED_IMMUTABLE_PREFIX:
        issues.append("immutable_prefix does not match ConversationContext")
    if value["turn_group"] != EXPECTED_TURN_GROUP:
        issues.append("turn_group does not match ConversationContext")
    if value["pruning"] != EXPECTED_PRUNING:
        issues.append("pruning does not match ConversationContext")
    expected_safety = {
        "max_model_turns": WrapperSettings().max_model_turns,
        "classification_if_reached": "runner_error",
        "experiment_performance_limit": False,
    }
    if value["internal_safety_guard"] != expected_safety:
        issues.append("internal_safety_guard does not match WrapperSettings")
    pending = value["pending_decisions"]
    if value["status"] == "CANDIDATE":
        if pending != EXPECTED_CANDIDATE_CONTEXT_PENDING:
            issues.append("candidate pending_decisions must contain max_context_characters")
    elif value["status"] == "FROZEN" and pending != []:
        issues.append("frozen context policy must have no pending decisions")
    _validate_notes(value["notes"], "notes", issues)
    return issues


def validate_execution_limits(
    value: dict[str, Any], *, require_frozen: bool = False
) -> list[str]:
    issues, complete = _check_top_fields(value, EXECUTION_FIELDS, "execution-limit")
    if not complete:
        return issues
    _validate_common_status(value, require_frozen=require_frozen, issues=issues)
    wall = value["common_task_wall_clock"]
    expected_wall_keys = {
        "applies_to_systems",
        "seconds",
        "selection_status",
        "same_value_for_all_systems",
        "required_before_main_experiment",
        "stop_transition",
        "stop_reason",
    }
    if not isinstance(wall, dict) or set(wall) != expected_wall_keys:
        issues.append("common_task_wall_clock has unexpected structure")
    else:
        if wall["applies_to_systems"] != ALL_SYSTEMS:
            issues.append("task wall clock must apply to the exact four evaluated systems")
        for field, expected in (
            ("same_value_for_all_systems", True),
            ("required_before_main_experiment", True),
            ("stop_transition", "suspended"),
            ("stop_reason", "task_wall_clock_limit"),
        ):
            if wall[field] != expected:
                issues.append(f"common_task_wall_clock.{field} must equal {expected!r}")

    api = value["api_wrapper_limits"]
    expected_api_keys = {
        "applies_to_systems",
        "api_action_limit",
        "command_timeout_seconds",
        "consecutive_no_action_response_limit",
        "same_values_for_both_api_systems",
    }
    if not isinstance(api, dict) or set(api) != expected_api_keys:
        issues.append("api_wrapper_limits has unexpected structure")
        action = None
        command = None
        no_action = None
    else:
        if api["applies_to_systems"] != API_SYSTEMS:
            issues.append("API limits must apply to the exact two shared-wrapper systems")
        if api["same_values_for_both_api_systems"] is not True:
            issues.append("same_values_for_both_api_systems must be true")
        action = api["api_action_limit"]
        command = api["command_timeout_seconds"]
        no_action = api["consecutive_no_action_response_limit"]

    expected_action_keys = {
        "pilot_start_value",
        "frozen_value",
        "selection_status",
        "counted_event",
        "multiple_calls_count_separately",
        "malformed_arguments_for_known_tool_count",
        "unknown_tool_calls_count",
        "provider_retries_count",
        "submission_counts",
        "stop_transition",
        "stop_reason",
    }
    if not isinstance(action, dict) or set(action) != expected_action_keys:
        issues.append("api_action_limit has unexpected structure")
    else:
        expected_action = {
            "pilot_start_value": PILOT_API_ACTION_LIMIT,
            "counted_event": "accepted known logical tool call reaching the executor",
            "multiple_calls_count_separately": True,
            "malformed_arguments_for_known_tool_count": True,
            "unknown_tool_calls_count": False,
            "provider_retries_count": False,
            "submission_counts": False,
            "stop_transition": "suspended",
            "stop_reason": "api_action_limit",
        }
        for field, expected in expected_action.items():
            if action[field] != expected:
                issues.append(f"api_action_limit.{field} must equal {expected!r}")

    expected_command_keys = {
        "pilot_start_value",
        "frozen_value",
        "selection_status",
        "scope",
        "stop_transition",
        "stop_reason",
    }
    if not isinstance(command, dict) or set(command) != expected_command_keys:
        issues.append("command_timeout_seconds has unexpected structure")
    else:
        expected_command = {
            "pilot_start_value": PILOT_COMMAND_TIMEOUT_SECONDS,
            "scope": "each accepted execute_bash call",
            "stop_transition": "suspended",
            "stop_reason": "command_timeout",
        }
        for field, expected in expected_command.items():
            if command[field] != expected:
                issues.append(f"command_timeout_seconds.{field} must equal {expected!r}")

    expected_no_action = {
        "frozen_value",
        "selection_status",
        "counted_event",
        "reset_event",
        "provider_retries_count",
        "stop_transition",
        "stop_reason",
    }
    if not isinstance(no_action, dict) or set(no_action) != expected_no_action:
        issues.append("consecutive_no_action_response_limit has unexpected structure")
    else:
        expected_values = {
            "frozen_value": PILOT_CONSECUTIVE_NO_ACTION_RESPONSE_LIMIT,
            "selection_status": "selected_from_l1_canary_review",
            "counted_event": "model response with neither an accepted known logical tool call reaching the executor nor the exact submit marker",
            "reset_event": "accepted known logical tool call reaching the executor",
            "provider_retries_count": False,
            "stop_transition": "suspended",
            "stop_reason": "protocol_no_progress_limit",
        }
        for field, expected in expected_values.items():
            if no_action[field] != expected:
                issues.append(
                    f"consecutive_no_action_response_limit.{field} must equal {expected!r}"
                )

    status = value["status"]
    scope = value["freeze_scope"]
    if status == "CANDIDATE":
        if isinstance(wall, dict):
            if wall.get("seconds") is not None:
                issues.append("candidate task wall clock must remain null")
            if wall.get("selection_status") != "pending_16_run_pilot":
                issues.append("candidate task wall-clock selection must remain pending")
        for label, item in (("api_action_limit", action), ("command_timeout_seconds", command)):
            if isinstance(item, dict):
                if item.get("frozen_value") is not None:
                    issues.append(f"candidate {label}.frozen_value must remain null")
                if item.get("selection_status") != "pending_pilot_review":
                    issues.append(f"candidate {label}.selection_status must remain pending")
        if value["pending_decisions"] != EXPECTED_CANDIDATE_EXECUTION_PENDING:
            issues.append("candidate execution pending_decisions do not match open values")
    elif status == "FROZEN":
        if isinstance(action, dict):
            if not _positive_integer(action.get("frozen_value")):
                issues.append("frozen api_action_limit.frozen_value must be positive")
        if isinstance(command, dict):
            if not _positive_integer(command.get("frozen_value")):
                issues.append("frozen command_timeout_seconds.frozen_value must be positive")
        if scope == "pilot_candidate":
            for label, item in (("api_action_limit", action), ("command_timeout_seconds", command)):
                if isinstance(item, dict) and item.get("selection_status") != "selected_for_pilot":
                    issues.append(f"pilot {label}.selection_status must be selected_for_pilot")
            if isinstance(wall, dict):
                seconds = wall.get("seconds")
                wall_status = wall.get("selection_status")
                if not _positive_integer(seconds) or wall_status != "selected_for_pilot":
                    issues.append(
                        "pilot task wall clock must be a positive provisional value "
                        "with selection_status selected_for_pilot"
                    )
            if value["pending_decisions"] != []:
                issues.append("pilot execution limits must have no pending decisions")
        elif scope == "main_experiment":
            if not isinstance(wall, dict) or not _positive_integer(wall.get("seconds")):
                issues.append("main task wall-clock seconds must be a positive integer")
            elif wall.get("selection_status") != "selected_and_frozen":
                issues.append("main task wall-clock selection_status must be selected_and_frozen")
            for label, item in (("api_action_limit", action), ("command_timeout_seconds", command)):
                if isinstance(item, dict) and item.get("selection_status") != "selected_and_frozen":
                    issues.append(f"main {label}.selection_status must be selected_and_frozen")
            if value["pending_decisions"] != []:
                issues.append("main execution limits must have no pending decisions")

    if value["pre_freeze_adjustment"] != EXPECTED_ADJUSTMENT_POLICY:
        issues.append("pre_freeze_adjustment does not match the approved one-adjustment rule")
    if value["limit_event_outcome"] != EXPECTED_LIMIT_OUTCOME:
        issues.append("limit_event_outcome does not match the terminal-state protocol")
    _validate_notes(value["notes"], "notes", issues)
    return issues


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate context and execution-limit configuration candidates."
    )
    parser.add_argument(
        "--context-policy",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "context_policy.candidate.json",
    )
    parser.add_argument(
        "--execution-limits",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "execution_limits.candidate.json",
    )
    parser.add_argument("--require-frozen", action="store_true")
    arguments = parser.parse_args()
    try:
        context = _load_object(arguments.context_policy)
        execution = _load_object(arguments.execution_limits)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1) from error
    issues = [
        "context_policy: " + issue
        for issue in validate_context_policy(
            context, require_frozen=arguments.require_frozen
        )
    ]
    issues.extend(
        "execution_limits: " + issue
        for issue in validate_execution_limits(
            execution, require_frozen=arguments.require_frozen
        )
    )
    if arguments.require_frozen and not issues:
        if context["freeze_scope"] != execution["freeze_scope"]:
            issues.append("freeze_scope must match across context and execution policies")
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid_context_policy={arguments.context_policy.resolve()}")
    print(f"context_policy_sha256={file_sha256(arguments.context_policy)}")
    print(f"valid_execution_limits={arguments.execution_limits.resolve()}")
    print(f"execution_limits_sha256={file_sha256(arguments.execution_limits)}")


if __name__ == "__main__":
    main()
