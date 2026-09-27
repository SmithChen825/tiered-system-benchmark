# Unified main-experiment dataset

This directory assembles **144 selected valid observations** (12 tasks × 4 systems × 3 repetitions) from the published L1–L4 exports. Pilot runs are excluded. This release performs data preparation and validation only: no statistical comparisons, confidence intervals, hypothesis tests or thesis figures are generated.

## Reproduce and verify

From the repository root with Python 3.12 (standard library only; no package installation or model account):

```sh
python analysis/build_dataset.py
python analysis/build_dataset.py --check
python -m unittest discover -s analysis -p "test_build_dataset.py"
```

The first command regenerates `analysis_dataset.csv` and `validation_summary.json`. `--check` recomputes both and checks exact UTF-8 bytes without writing. It fails if a source invariant or committed output is inconsistent. No source exports are modified. Paths are resolved from the script location, not the terminal's working directory.

## Files and provenance

- [analysis_dataset.csv](analysis_dataset.csv): one row per selected scheduled task–system–repetition slot, sorted by global position.
- [validation_summary.json](validation_summary.json): population, stopping and missingness counts plus checks and limitations. This is a validation summary, not a performance ranking.
- [build_dataset.py](../../analysis/build_dataset.py): inspectable transformation and validation rules.
- [test_build_dataset.py](../../analysis/test_build_dataset.py): regression checks for duplicate records, missing joins, invalid selections and limit-stopped success.

Sources are `data/L1/` through `data/L4/` (`selected_runs.json` and `all_attempts.json`), `benchmark/config/run_schedule.main.json`, and the original/reviewed score and selection files in `data/evaluation-review/`. The initial assembly uses the public files at repository commit `453302a29fbab2bc1fdcf05eecaa526887f8d741`; subsequent rebuilds use the files in the checked-out repository. Record the repository commit when using this dataset in an analysis.

The 155 retained attempts yield 144 selected observations and 11 exclusions. Selection follows the published analytical attempt indexes, including post-run adjudications, rather than filtering sealed mechanical validity alone. The scheduled a01 identifier does not replace a selected a02/a03. Each selected ID must match both score tables exactly.

L1/L2 keep original scoring in their detailed exports; L3/L4 also carry reviewed summaries. All four tiers use the same separately versioned `public-contract-audit/2026-09-26` review for the unified reviewed columns. Embedded L3/L4 summaries are cross-checked. Never apply the old L4-02 adjustment again.

## Field dictionary

CSV uses UTF-8, a header and comma separation. Binary indicators are integers 0/1. Empty cells mean null/unavailable or not applicable as specified below; they never mean zero. Counts are integers, proportions and seconds numeric, and other populated fields strings. No missing usage or cost is imputed.

| Column(s) | Meaning and source |
|---|---|
| `global_position` | Original schedule position, 1–144; ordering is not performance rank. |
| `run_id` | Unique selected attempt identifier; join key to detailed source records and score review. |
| `task_id`, `tier` | Task L1-01 through L4-03; architectural tier integer 1–4. |
| `system_id` | Recorded configured system: cursor, devin, gpt-5.4 or qwen2.5-coder-7b-instruct. |
| `repetition`, `attempt`, `order_position` | Repetition 1–3; selected attempt number; system execution position 1–4 in that task/repetition block. |
| `validity_status` | Always valid for the 144 selected observations; excluded attempts stay in the source indexes. |
| `original_lifecycle_state` | Recorded successful/unsuccessful state under original scoring. It may differ from reviewed success. |
| `stop_reason`, `normal_submission` | Recorded stopping reason and indicator that it equals submitted. A protocol_no_progress_limit stop remains unsuccessful. |
| `started_at`, `ended_at` | Recorded timezone-aware ISO timestamps, preserved as supplied. |
| `elapsed_seconds` | Recorded elapsed task duration; includes native permission waits, excludes subsequent hidden evaluation. Not recomputed from timestamp rounding. |
| `original_success`, `reviewed_success` | Binary run outcome under each scoring version. Both require normal submission and every applicable functional and architecture check passing. |
| `review_version` | Version of the separate post-outcome scoring review. Original source records remain unchanged. |
| `original_functional_passed`, `original_functional_applicable`, `original_functional_proportion` | Original functional passed count, denominator and passed/applicable. |
| `original_architecture_passed`, `original_architecture_applicable`, `original_architecture_proportion` | Original architecture passed count, denominator and passed/applicable. |
| `reviewed_functional_passed`, `reviewed_functional_applicable`, `reviewed_functional_proportion` | Reviewed functional diagnostic counts and proportion. |
| `reviewed_architecture_passed`, `reviewed_architecture_applicable`, `reviewed_architecture_proportion` | Reviewed architecture diagnostic counts and proportion. Functional and architecture diagnostics remain separate; no aggregate weighted score. |
| `clarification_opportunity` | 1 only for L2-02: 12 observations (3 per system); other 132 have complete-brief classification. |
| `clarification_requests`, `clarification_authorized_requests`, `clarification_responses` | Preserved recorded request/authorized request/evaluator response counts. Permission approvals are excluded. These are inputs to later behavior analysis, not newly adjudicated transcript counts. |
| `robustness_eligible` | 1 for L3/L4 only, 72 observations (18 per system). |
| `original_autonomous_success`, `reviewed_autonomous_success` | For eligible rows, success in the corresponding version and zero evaluator clarification responses. Blank outside L3/L4. This does not independently measure recovery from every fault. |
| `usage_status` | Recorded usage availability status. Available token counts do not imply available cost. |
| `usage_input_tokens`, `usage_output_tokens`, `usage_total_tokens` | Recorded token counts; blank when unavailable. Not comparable to unrecorded native usage. |
| `usage_monetary_cost`, `usage_currency` | Recorded per-run cost and currency, blank if unavailable. Account-level billing was not allocated to runs. |
| `evaluation_interface`, `product_version`, `model_identifier`, `configuration_sha256` | Recorded configuration provenance. Product version may be blank for API interfaces. |
| `start_commit` | Recorded deterministic task starting commit. |
| `source_selected_runs` | Repository-relative detailed source file; locate its row by run_id. |

## Scope and interpretation

The generator checks unique slots, schedule identities, attempt selection, complete score joins, original individual checks, counts/proportions, both success gates, stopping totals, basic timing and usage validity, and behavior population definitions. All valid failures remain in the dataset. It preserves the recorded source evidence boundaries; these checks are not fresh deployment tests or proof that every hidden evaluator is complete.

Final diffs, check-level evidence and exclusion details remain in the source JSON files instead of being duplicated into each CSV cell. Raw conversations, permission histories and billing archives are not added. Partial native transcripts and unknown permission-event counts remain limitations. Cost/usage comparisons require care because native usage is unavailable.

Later statistical work should use one explicitly declared scoring version consistently, retain the same 144 slots for sensitivity comparisons and preserve task-level grouping. This branch does not execute that analysis or settle the final interpretation.
