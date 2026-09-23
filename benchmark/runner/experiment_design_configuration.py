from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import REPOSITORY_ROOT, SYSTEM_PROFILES, build_run_id
from .task_evaluation_configuration import validate_task_set


SCHEMA_VERSION = "1.0.0"
PILOT_SEED = "tsb-pilot-2026-v1"
MAIN_SEED = "tsb-main-2026-v1"
EVALUATED_SYSTEMS = [
    "cursor",
    "devin",
    "gpt-5.4",
    "qwen2.5-coder-7b-instruct",
]
PAIRWISE_SYSTEMS = [
    [EVALUATED_SYSTEMS[left], EVALUATED_SYSTEMS[right]]
    for left in range(len(EVALUATED_SYSTEMS))
    for right in range(left + 1, len(EVALUATED_SYSTEMS))
]
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SCHEDULE_ALGORITHM = {
    "id": "sha256_seeded_rank_v1",
    "definition": "Within each task-repetition block, sort systems by SHA-256 rank digest.",
    "rank_input": "seed NUL phase NUL task_id NUL repetition_decimal NUL system_id",
    "encoding": "utf-8",
    "tie_break": "system_id_ascending",
}
SCHEDULE_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "schedule_id",
    "phase",
    "task_set",
    "seed",
    "permutation_algorithm",
    "systems",
    "repetitions_per_task",
    "attempt",
    "block_definition",
    "entries",
    "entry_count",
    "entries_sha256",
    "pending_main_schedule",
    "notes",
}
ENTRY_FIELDS = {
    "global_position",
    "block_id",
    "task_id",
    "tier",
    "repetition",
    "order_position",
    "system_id",
    "system_slug",
    "run_id",
}
ANALYSIS_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "analysis_plan_id",
    "applies_to",
    "source_contracts",
    "population",
    "primary_outcome",
    "diagnostic_outcomes",
    "success_summaries",
    "pairwise_comparisons",
    "timing_analysis",
    "clarification_analysis",
    "robustness_analysis",
    "qualitative_failure_analysis",
    "missingness_and_invalid_runs",
    "prohibited_methods",
    "reproducibility",
    "pending_decisions",
    "notes",
}
EXPECTED_PENDING = [
    "analysis_package_versions",
    "final_main_schedule_sha256",
]
BOOTSTRAP_INTERVAL_METHOD = "percentile_two_sided_95"
PAIRWISE_P_VALUE_METHOD = "exact_paired_task_label_swap_two_sided_4096"
BOOTSTRAP_RANDOM_SEED = "tsb-main-bootstrap-2026-v1"
FINAL_MAIN_SCHEDULE_SHA256 = "2480e337766e7a5b08f0530e70c30bc86ef1ff75b579201afd7139b4285a2e72"
ANALYSIS_PACKAGE_VERSIONS = {
    "python": "3.12.13",
    "numpy": "2.3.5",
    "pandas": "3.0.1",
    "python-dateutil": "2.9.0.post0",
    "six": "1.17.0",
    "tzdata": "2026.3",
}
EXPECTED_TABLE_IDS = [
    "run_flow",
    "overall_system_success",
    "tier_system_success",
    "task_system_success",
    "pairwise_risk_differences",
    "elapsed_time",
    "clarification_funnel",
    "diagnostic_correctness",
    "robustness",
    "failure_categories",
]
RESULT_TABLES_SHA256 = "bd025488b1110fbd33623c57377d5120225359328063ec970bf56b6275ce322a"
EXPECTED_POPULATION = {
    "analysis_unit": "scheduled_task_system_repetition_slot",
    "systems": EVALUATED_SYSTEMS,
    "tasks_per_tier": 3,
    "tiers": [1, 2, 3, 4],
    "valid_terminal_states": ["successful", "unsuccessful"],
    "invalidated_attempts_retained_but_not_scored": True,
}


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rank_digest(
    seed: str, phase: str, task_id: str, repetition: int, system_id: str
) -> str:
    material = "\0".join(
        (seed, phase, task_id, str(repetition), system_id)
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def generate_schedule_entries(
    *,
    seed: str,
    phase: str,
    tasks: list[dict[str, Any]],
    repetitions_per_task: int,
    attempt: int = 1,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    global_position = 1
    for task in tasks:
        task_id = task["task_id"]
        tier = task["tier"]
        for repetition in range(1, repetitions_per_task + 1):
            block_id = f"{task_id}-r{repetition:02d}"
            systems = sorted(
                EVALUATED_SYSTEMS,
                key=lambda system_id: (
                    _rank_digest(seed, phase, task_id, repetition, system_id),
                    system_id,
                ),
            )
            for order_position, system_id in enumerate(systems, 1):
                system_slug = SYSTEM_PROFILES[system_id][0]
                entries.append(
                    {
                        "global_position": global_position,
                        "block_id": block_id,
                        "task_id": task_id,
                        "tier": tier,
                        "repetition": repetition,
                        "order_position": order_position,
                        "system_id": system_id,
                        "system_slug": system_slug,
                        "run_id": build_run_id(
                            phase,
                            task_id,
                            system_slug,
                            repetition,
                            attempt,
                        ),
                    }
                )
                global_position += 1
    return entries


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _validate_status(
    value: dict[str, Any], *, require_frozen: bool, issues: list[str]
) -> None:
    status = value.get("status")
    scope = value.get("freeze_scope")
    if status not in {"CANDIDATE", "FROZEN"}:
        issues.append("status must be CANDIDATE or FROZEN")
    if status == "CANDIDATE" and scope is not None:
        issues.append("candidate freeze_scope must be null")
    if status == "FROZEN" and scope not in {"pilot_candidate", "main_experiment"}:
        issues.append("frozen freeze_scope must be pilot_candidate or main_experiment")
    if require_frozen and status != "FROZEN":
        issues.append("status must be FROZEN for experiment execution")


def _validate_path_hash(
    record: Any,
    *,
    expected_path: str,
    repository_root: Path,
    label: str,
    issues: list[str],
) -> Path | None:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        issues.append(f"{label} must contain path and sha256")
        return None
    if record.get("path") != expected_path:
        issues.append(f"{label}.path must equal {expected_path}")
        return None
    path = (repository_root / expected_path).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        issues.append(f"{label}.path escapes the repository")
        return None
    if not path.is_file():
        issues.append(f"{label}.path does not exist")
        return None
    observed = file_sha256(path)
    if record.get("sha256") != observed:
        issues.append(f"{label}.sha256 mismatch")
    return path


def validate_schedule(
    value: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    task_set: dict[str, Any] | None = None,
    require_frozen: bool = False,
) -> list[str]:
    issues: list[str] = []
    if set(value) != SCHEDULE_FIELDS:
        return ["schedule fields do not match the contract"]
    if value["schema_version"] != SCHEMA_VERSION:
        issues.append("schedule schema_version mismatch")
    _validate_status(value, require_frozen=require_frozen, issues=issues)
    status = value["status"]
    expected_task_set_path = (
        "benchmark/config/task_set.candidate.json"
        if status == "CANDIDATE"
        else "benchmark/config/task_set.main.json"
        if value["freeze_scope"] == "main_experiment"
        else "benchmark/config/task_set.json"
    )
    task_set_path = _validate_path_hash(
        value["task_set"],
        expected_path=expected_task_set_path,
        repository_root=repository_root,
        label="task_set",
        issues=issues,
    )
    if task_set is None and task_set_path is not None:
        task_set = _load_object(task_set_path)
    if not isinstance(task_set, dict) or not isinstance(task_set.get("tasks"), list):
        return issues + ["task_set is unavailable or invalid"]
    issues.extend(
        "task_set: " + issue
        for issue in validate_task_set(
            task_set,
            repository_root=repository_root,
            require_frozen=require_frozen,
        )
    )
    implemented_tasks = [
        {"task_id": task["task_id"], "tier": task["tier"]}
        for task in task_set["tasks"]
        if task.get("implementation_status") == "implementation_validated"
    ]
    if value["systems"] != EVALUATED_SYSTEMS:
        issues.append("systems must use the canonical four-system order")
    if value["permutation_algorithm"] != SCHEDULE_ALGORITHM:
        issues.append("permutation_algorithm mismatch")
    if value["block_definition"] != "task_id_x_repetition":
        issues.append("block_definition must be task_id_x_repetition")
    if value["attempt"] != 1:
        issues.append("the scheduled attempt must be 1")
    phase = value["phase"]
    repetitions = value["repetitions_per_task"]
    if status == "CANDIDATE":
        if phase == "pilot":
            if repetitions != 1 or value["seed"] != PILOT_SEED:
                issues.append("pilot candidate must retain the fixed one-repetition seed")
            if value["schedule_id"] != "tsb-pilot-schedule-v1":
                issues.append("pilot candidate schedule_id mismatch")
            if value["pending_main_schedule"] is not True:
                issues.append("pilot candidate must record the main schedule as pending")
        elif phase == "main":
            if repetitions != 3 or len(implemented_tasks) != 12:
                issues.append("main candidate requires 12 implemented tasks and three repetitions")
            if value["seed"] != MAIN_SEED:
                issues.append("main candidate must retain the fixed public main seed")
            if value["schedule_id"] != "tsb-main-schedule-v1":
                issues.append("main candidate schedule_id mismatch")
            if value["pending_main_schedule"] is not False:
                issues.append("main candidate cannot leave the main schedule pending")
        else:
            issues.append("candidate phase must be pilot or main")
    elif value["freeze_scope"] == "pilot_candidate":
        if phase != "pilot" or repetitions != 1:
            issues.append("pilot freeze requires one repetition per representative task")
    elif value["freeze_scope"] == "main_experiment":
        if phase != "main" or repetitions != 3 or len(implemented_tasks) != 12:
            issues.append("main freeze requires 12 implemented tasks and three repetitions")
        if value["pending_main_schedule"] is not False:
            issues.append("main freeze cannot leave the main schedule pending")
    seed = value["seed"]
    if not isinstance(seed, str) or not seed:
        issues.append("seed must be a non-empty string")
        return issues
    expected_entries = generate_schedule_entries(
        seed=seed,
        phase=phase,
        tasks=implemented_tasks,
        repetitions_per_task=repetitions,
        attempt=value["attempt"],
    )
    entries = value["entries"]
    if not isinstance(entries, list):
        return issues + ["entries must be a list"]
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            issues.append(f"entries[{index}] fields do not match the contract")
    if entries != expected_entries:
        issues.append("entries do not match the deterministic seeded schedule")
    if value["entry_count"] != len(entries):
        issues.append("entry_count mismatch")
    if value["entries_sha256"] != canonical_json_sha256(entries):
        issues.append("entries_sha256 mismatch")
    run_ids = [entry.get("run_id") for entry in entries if isinstance(entry, dict)]
    if len(run_ids) != len(set(run_ids)):
        issues.append("run IDs must be unique")
    if not isinstance(value["notes"], list) or not value["notes"]:
        issues.append("notes must be a non-empty list")
    return issues


def validate_result_tables(value: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if set(value) != {
        "schema_version",
        "status",
        "table_set_id",
        "tables",
        "notes",
    }:
        return ["result-table fields do not match the contract"]
    if value["schema_version"] != SCHEMA_VERSION or value["status"] not in {"CANDIDATE", "FROZEN"}:
        issues.append("result tables must be a version 1.0.0 candidate or frozen set")
    tables = value["tables"]
    if not isinstance(tables, list):
        return issues + ["tables must be a list"]
    ids = [table.get("table_id") for table in tables if isinstance(table, dict)]
    if ids != EXPECTED_TABLE_IDS:
        issues.append("result table IDs or order do not match the analysis contract")
    for index, table in enumerate(tables):
        if not isinstance(table, dict) or set(table) != {
            "table_id",
            "title",
            "grain",
            "columns",
        }:
            issues.append(f"tables[{index}] structure is invalid")
            continue
        if not isinstance(table["columns"], list) or not table["columns"]:
            issues.append(f"tables[{index}].columns must be non-empty")
        elif len(table["columns"]) != len(set(table["columns"])):
            issues.append(f"tables[{index}].columns contains duplicates")
    if canonical_json_sha256(tables) != RESULT_TABLES_SHA256:
        issues.append("result table definitions have drifted")
    return issues


def validate_analysis_plan(
    value: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    require_frozen: bool = False,
) -> list[str]:
    issues: list[str] = []
    if set(value) != ANALYSIS_FIELDS:
        return ["analysis-plan fields do not match the contract"]
    if value["schema_version"] != SCHEMA_VERSION:
        issues.append("analysis-plan schema_version mismatch")
    _validate_status(value, require_frozen=require_frozen, issues=issues)
    if value["analysis_plan_id"] != "tsb-main-analysis-v1":
        issues.append("analysis_plan_id mismatch")
    if value["applies_to"] != {
        "phase": "main",
        "scheduled_runs": 144,
        "tasks": 12,
        "systems": 4,
        "repetitions_per_task": 3,
        "pilot_runs_excluded": True,
    }:
        issues.append("applies_to does not match the 144-run main design")
    contracts = value["source_contracts"]
    result_tables_path = (
        "benchmark/config/result_tables.main.json"
        if value["status"] == "FROZEN"
        else "benchmark/config/result_tables.candidate.json"
    )
    expected_contract_paths = {
        "run_metadata_schema": "benchmark/schemas/run_metadata.schema.json",
        "analysis_output_schema": "benchmark/schemas/analysis_output.schema.json",
        "result_tables": result_tables_path,
    }
    resolved_contracts: dict[str, Path] = {}
    if not isinstance(contracts, dict) or set(contracts) != set(expected_contract_paths):
        issues.append("source_contracts keys are invalid")
    else:
        for label, path in expected_contract_paths.items():
            resolved = _validate_path_hash(
                contracts[label],
                expected_path=path,
                repository_root=repository_root,
                label=f"source_contracts.{label}",
                issues=issues,
            )
            if resolved is not None:
                resolved_contracts[label] = resolved
    output_schema_path = resolved_contracts.get("analysis_output_schema")
    if output_schema_path is not None:
        output_schema = _load_object(output_schema_path)
        expected_output_fields = [
            "schema_version",
            "provenance",
            *EXPECTED_TABLE_IDS,
        ]
        if (
            output_schema.get("$schema")
            != "https://json-schema.org/draft/2020-12/schema"
            or output_schema.get("additionalProperties") is not False
            or output_schema.get("required") != expected_output_fields
        ):
            issues.append("analysis output schema top-level contract mismatch")
    primary = value["primary_outcome"]
    if primary != {
        "name": "binary_run_success",
        "symbol": "Y_s_i_r",
        "success_value": 1,
        "failure_value": 0,
        "success_rule": "all_applicable_functional_tests_and_architecture_invariants_pass",
        "primary_estimand": "system_success_rate",
        "main_denominator_per_system": 36,
    }:
        issues.append("primary_outcome must remain binary final-state success")
    if value["diagnostic_outcomes"] != {
        "measures": ["C_func", "C_arch"],
        "reported_separately": True,
        "may_override_primary_outcome": False,
        "weighted_aggregate": None,
    }:
        issues.append("diagnostic outcomes must keep C_func and C_arch separate")
    if value["success_summaries"] != {
        "levels": ["overall_by_system", "tier_by_system", "task_by_system"],
        "interval": "wilson_95_percent",
        "heatmap": "task_by_system_success_rate",
    }:
        issues.append("success summary methods mismatch")
    pairwise = value["pairwise_comparisons"]
    if not isinstance(pairwise, dict):
        issues.append("pairwise_comparisons must be an object")
    else:
        fixed_pairwise = copy.deepcopy(pairwise)
        interval_method = fixed_pairwise.pop("bootstrap_interval_method", None)
        p_value_method = fixed_pairwise.pop("p_value_method", None)
        if fixed_pairwise != {
            "systems": EVALUATED_SYSTEMS,
            "contrasts": PAIRWISE_SYSTEMS,
            "effect_measure": "risk_difference_system_a_minus_system_b",
            "resampling_unit": "task",
            "bootstrap_resamples": 10000,
            "retain_within_resample": "all_four_systems_and_all_three_repetitions",
            "multiplicity_adjustment": "holm_for_six_pairwise_contrasts",
            "familywise_alpha": 0.05,
        }:
            issues.append("pairwise comparison design mismatch")
        if interval_method != BOOTSTRAP_INTERVAL_METHOD:
            issues.append("bootstrap interval method must remain the approved two-sided percentile method")
        if p_value_method != PAIRWISE_P_VALUE_METHOD:
            issues.append("pairwise p-value method must remain the approved exact paired task-label-swap test")
    expected_simple_sections = {
        "timing_analysis": {
            "summaries": ["median", "interquartile_range"],
            "populations": ["successful_valid_runs", "all_valid_runs"],
            "measure": "elapsed_seconds",
        },
        "clarification_analysis": {
            "metrics": [
                "opportunity_capture",
                "request_precision",
                "unnecessary_request_rate",
            ],
            "opportunity_runs_total": 12,
            "opportunity_runs_per_system": 3,
            "complete_brief_runs_total": 132,
            "complete_brief_runs_per_system": 33,
            "permission_approvals_excluded": True,
        },
        "robustness_analysis": {
            "eligible_tiers": [3, 4],
            "eligible_tasks": 6,
            "denominator_per_system": 18,
            "numerator": "successful_runs_without_evaluator_response",
        },
        "prohibited_methods": [
            "weighted_aggregate_score",
            "mixed_effects_primary_model",
            "private_reasoning_inference",
            "imputation_of_unavailable_native_usage_or_cost",
        ],
    }
    for label, expected in expected_simple_sections.items():
        if value[label] != expected:
            issues.append(f"{label} mismatch")
    qualitative = value["qualitative_failure_analysis"]
    expected_categories = [
        "premature_submission",
        "repeated_ineffective_commands",
        "incorrect_api_or_database_assumption",
        "missed_cascading_dependency",
        "unnecessary_clarification",
        "failed_final_state_validation",
        "other_evidence_supported",
    ]
    if qualitative != {
        "unit": "valid_unsuccessful_run",
        "categories": expected_categories,
        "multiple_categories_per_run": True,
        "evidence_reference_required": True,
        "private_reasoning_inference_prohibited": True,
    }:
        issues.append("qualitative failure plan mismatch")
    if value["missingness_and_invalid_runs"] != {
        "retain_invalidated_attempts": True,
        "exclude_invalidated_attempts_from_performance_denominators": True,
        "rerun_only_formally_invalid_attempts": True,
        "analysis_attempt_per_scheduled_slot": "first_valid_terminal_attempt",
        "agent_failures_and_limits_are_valid_unsuccessful": True,
        "unavailable_native_usage_or_cost": "report_unavailable_without_imputation",
    }:
        issues.append("missingness and invalid-run rules mismatch")
    reproducibility = value["reproducibility"]
    if not isinstance(reproducibility, dict) or set(reproducibility) != {
        "notebook_format",
        "bootstrap_random_seed",
        "package_versions",
        "final_main_schedule_sha256",
        "input_dataset_sha256_required",
        "analysis_script_sha256_required",
    }:
        issues.append("reproducibility structure mismatch")
    else:
        if reproducibility["notebook_format"] != "python_jupyter":
            issues.append("analysis notebook must use Python/Jupyter")
        if reproducibility["input_dataset_sha256_required"] is not True or reproducibility["analysis_script_sha256_required"] is not True:
            issues.append("dataset and script hashes are required")
        if reproducibility["bootstrap_random_seed"] != BOOTSTRAP_RANDOM_SEED:
            issues.append("analysis must retain the approved seed for bootstrap resampling")
        if reproducibility["package_versions"] != ANALYSIS_PACKAGE_VERSIONS:
            issues.append("analysis package versions do not match the frozen minimal stack")
        if (
            value["status"] == "CANDIDATE"
            and reproducibility["final_main_schedule_sha256"] != FINAL_MAIN_SCHEDULE_SHA256
        ):
            issues.append("analysis plan does not bind the verified final main schedule hash")
        schedule_path = repository_root / "benchmark" / "config" / (
            "run_schedule.main.json"
            if value["status"] == "FROZEN"
            else "run_schedule.candidate.json"
        )
        expected_schedule_hash = (
            file_sha256(schedule_path) if schedule_path.is_file() else None
        )
        if value["status"] == "CANDIDATE" and expected_schedule_hash != FINAL_MAIN_SCHEDULE_SHA256:
            issues.append("bound final main schedule file is absent or has drifted")
        if reproducibility["final_main_schedule_sha256"] != expected_schedule_hash:
            issues.append("analysis plan does not bind its status-matched main schedule file")
    if value["status"] == "CANDIDATE":
        if value["pending_decisions"] != []:
            issues.append("completed analysis candidate cannot retain pending decisions")
    elif value["pending_decisions"] != []:
        issues.append("frozen analysis plan cannot have pending decisions")
    if value["population"] != EXPECTED_POPULATION:
        issues.append("population does not match the frozen 144-run design")
    if not isinstance(value["notes"], list) or not value["notes"]:
        issues.append("notes must be a non-empty list")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate seeded schedule and analysis-plan candidates."
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "run_schedule.candidate.json",
    )
    parser.add_argument(
        "--analysis-plan",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "analysis_plan.candidate.json",
    )
    parser.add_argument(
        "--result-tables",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "result_tables.candidate.json",
    )
    parser.add_argument("--require-frozen", action="store_true")
    arguments = parser.parse_args()
    try:
        schedule = _load_object(arguments.schedule)
        analysis = _load_object(arguments.analysis_plan)
        tables = _load_object(arguments.result_tables)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1) from error
    issues = ["schedule: " + issue for issue in validate_schedule(schedule, require_frozen=arguments.require_frozen)]
    issues.extend("analysis_plan: " + issue for issue in validate_analysis_plan(analysis, require_frozen=arguments.require_frozen))
    issues.extend("result_tables: " + issue for issue in validate_result_tables(tables))
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid_schedule={arguments.schedule.resolve()}")
    print(f"schedule_sha256={file_sha256(arguments.schedule)}")
    print(f"schedule_entries_sha256={schedule['entries_sha256']}")
    print(f"valid_analysis_plan={arguments.analysis_plan.resolve()}")
    print(f"analysis_plan_sha256={file_sha256(arguments.analysis_plan)}")
    print(f"valid_result_tables={arguments.result_tables.resolve()}")
    print(f"result_tables_sha256={file_sha256(arguments.result_tables)}")


if __name__ == "__main__":
    main()
