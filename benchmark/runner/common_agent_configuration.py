from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .api_wrapper.contracts import (
    LOGICAL_TOOL_NAMES,
    SUBMIT_MARKER,
    TOOL_DEFINITIONS,
    TRANSPORT_CONTRACT_VERSION,
)
from .common import REPOSITORY_ROOT


SCHEMA_VERSION = "1.0.0"
SCHEMA_FIELDS = {
    "schema_version",
    "status",
    "transport_contract_version",
    "source",
    "logical_tool_names",
    "tool_definitions",
    "tool_definitions_sha256",
    "submission",
    "action_accounting",
    "execution_semantics",
}
EXPECTED_SOURCE = {
    "path": "benchmark/runner/api_wrapper/contracts.py",
    "symbol": "TOOL_DEFINITIONS",
}
EXPECTED_SUBMISSION = {
    "marker": SUBMIT_MARKER,
    "detection": "substring_in_observable_assistant_text",
    "counts_as_action": False,
    "terminal_state": "submitted",
    "tool_calls_in_same_turn": "recorded_but_not_executed",
}
EXPECTED_ACTION_ACCOUNTING = {
    "known_tool_call_reaching_executor": 1,
    "malformed_arguments_for_known_tool": 1,
    "unknown_tool_call": 0,
    "provider_retry": 0,
    "submission": 0,
    "multiple_calls_count_separately": True,
}
EXPECTED_EXECUTION_SEMANTICS = {
    "multiple_tool_calls": "provider_order_sequential",
    "tool_result_visibility": "returned_before_next_model_turn",
    "ordinary_tool_error": "observable_nonterminal",
    "command_timeout": "suspend_run",
    "tool_infrastructure_error": "invalidate_run",
    "default_network_access": False,
    "host_docker_access": False,
}
REQUIRED_PROMPT_FRAGMENTS = (
    "task-specific brief is supplied separately",
    "Work only within the supplied repository",
    "Do not modify tests or benchmark infrastructure",
    "read_file",
    "patch_file",
    "execute_bash",
    "request_human_clarification",
    "maximum duration of 180 seconds",
    SUBMIT_MARKER,
    "tool calls in that same response are recorded but not executed",
)
TASK_SPECIFIC_PROMPT_FRAGMENTS = (
    "L1-01",
    "L2-02",
    "L3-01",
    "L4-01",
    "due_date",
    "users.age",
    "wildcard origin",
    "product images",
)


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def tool_definitions_sha256() -> str:
    return canonical_json_sha256(list(TOOL_DEFINITIONS))


def validate_common_system_prompt(
    prompt: str, *, api_action_limit: int = 15
) -> list[str]:
    issues: list[str] = []
    if not prompt.strip():
        return ["Common system prompt must be non-empty"]
    if "\r" in prompt:
        issues.append("Common system prompt must use LF line endings")
    for fragment in REQUIRED_PROMPT_FRAGMENTS:
        if fragment not in prompt:
            issues.append(f"Common system prompt is missing required text: {fragment}")
    action_fragment = f"maximum of {api_action_limit} accepted logical tool actions"
    if action_fragment not in prompt:
        issues.append(
            "Common system prompt is missing the configured action limit text: "
            + action_fragment
        )
    for fragment in TASK_SPECIFIC_PROMPT_FRAGMENTS:
        if fragment.casefold() in prompt.casefold():
            issues.append(f"Common system prompt contains task-specific text: {fragment}")
    if prompt.count(SUBMIT_MARKER) != 1:
        issues.append("Common system prompt must contain the submit marker exactly once")
    return issues


def validate_tool_action_schema(
    value: dict[str, Any], *, require_frozen: bool = False
) -> list[str]:
    issues: list[str] = []
    missing = sorted(SCHEMA_FIELDS - set(value))
    unexpected = sorted(set(value) - SCHEMA_FIELDS)
    if missing:
        issues.append("Missing top-level fields: " + ", ".join(missing))
    if unexpected:
        issues.append("Unexpected top-level fields: " + ", ".join(unexpected))
    if missing:
        return issues
    if value["schema_version"] != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    if value["status"] not in {"CANDIDATE", "FROZEN"}:
        issues.append("status must be CANDIDATE or FROZEN")
    if require_frozen and value["status"] != "FROZEN":
        issues.append("status must be FROZEN before experiment execution")
    if value["transport_contract_version"] != TRANSPORT_CONTRACT_VERSION:
        issues.append("transport_contract_version does not match runner code")
    if value["source"] != EXPECTED_SOURCE:
        issues.append("source must identify the runner TOOL_DEFINITIONS symbol")
    if value["logical_tool_names"] != sorted(LOGICAL_TOOL_NAMES):
        issues.append("logical_tool_names do not match runner code")
    expected_definitions = list(TOOL_DEFINITIONS)
    if value["tool_definitions"] != expected_definitions:
        issues.append("tool_definitions do not exactly match runner code")
    observed_hash = tool_definitions_sha256()
    if value["tool_definitions_sha256"] != observed_hash:
        issues.append(
            "tool_definitions_sha256 mismatch: "
            f"expected {value['tool_definitions_sha256']}, observed {observed_hash}"
        )
    if value["submission"] != EXPECTED_SUBMISSION:
        issues.append("submission semantics do not match the shared runner")
    if value["action_accounting"] != EXPECTED_ACTION_ACCOUNTING:
        issues.append("action_accounting does not match the shared runner")
    if value["execution_semantics"] != EXPECTED_EXECUTION_SEMANTICS:
        issues.append("execution_semantics does not match the shared runner")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the common API-agent prompt and logical action schema."
    )
    parser.add_argument(
        "schema",
        type=Path,
        nargs="?",
        default=REPOSITORY_ROOT
        / "benchmark"
        / "config"
        / "tool_action_schema.candidate.json",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=REPOSITORY_ROOT
        / "benchmark"
        / "config"
        / "common_system_prompt.candidate.txt",
    )
    parser.add_argument("--require-frozen", action="store_true")
    parser.add_argument(
        "--api-action-limit",
        type=int,
        default=15,
        help="Expected accepted logical action limit stated in the prompt.",
    )
    arguments = parser.parse_args()
    try:
        schema = json.loads(arguments.schema.read_text(encoding="utf-8"))
        prompt = arguments.prompt.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1) from error
    if not isinstance(schema, dict):
        print("ERROR: Tool action schema must be a JSON object")
        raise SystemExit(1)
    issues = validate_tool_action_schema(
        schema, require_frozen=arguments.require_frozen
    )
    issues.extend(
        validate_common_system_prompt(
            prompt, api_action_limit=arguments.api_action_limit
        )
    )
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid_schema={arguments.schema.resolve()}")
    print(f"tool_definitions_sha256={tool_definitions_sha256()}")
    print(f"valid_prompt={arguments.prompt.resolve()}")
    print(f"prompt_sha256={prompt_sha256(prompt)}")


if __name__ == "__main__":
    main()
