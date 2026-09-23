# L1 experiment results

**36 completed main-experiment observations: 3 static-website tasks × 4 systems × 3 repetitions.**

## Results

| System | Successful runs | Success rate | L1-01 | L1-02 | L1-03 |
|---|---:|---:|---:|---:|---:|
| Cursor | 9/9 | 100% | 3/3 | 3/3 | 3/3 |
| Devin Desktop | 9/9 | 100% | 3/3 | 3/3 | 3/3 |
| GPT-5.4 | 9/9 | 100% | 3/3 | 3/3 | 3/3 |
| Qwen2.5-Coder-7B-Instruct | 0/9 | 0% | 0/3 | 0/3 | 0/3 |

Success requires normal submission and all applicable functional tests and architecture checks passing. These are descriptive L1 results, not a ranking across all four tiers.

- **L1-01:** product image paths — [task brief](../../benchmark/tasks/L1-01/public_task_brief.md).
- **L1-02:** responsive navigation — [task brief](../../benchmark/tasks/L1-02/public_task_brief.md).
- **L1-03:** client-side form validation — [task brief](../../benchmark/tasks/L1-03/public_task_brief.md).

## Files

- [selected_runs.json](selected_runs.json): 36 scored observations, including outcomes, timing, configuration identity, individual test/check results, usage when available, and final code diffs.
- [all_attempts.json](all_attempts.json): 41 recorded attempts, with selection and exclusion reasons and replacement links.

Records follow the frozen schedule's global positions 1–36. Each slot uses its first valid terminal attempt. Five GPT attempts were invalidated for infrastructure failures: three transport failures and two Docker evaluator access failures. Replacements are linked in the attempt index. Valid unsuccessful outcomes remain in the denominator.

All nine Qwen observations stopped at the consecutive no-action response limit. They remain unsuccessful observations under the recorded wrapper and model configuration.

## Reading the data

`timing.elapsed_seconds` is the recorded task duration; it excludes later hidden evaluation. `tests` and `checks` contain individual applicable/pass flags; `results` contains their totals. `final_diff` is the recorded workspace change relative to `start_commit`. `configuration_sha256` identifies each run's recorded configuration, rather than implying every run used an identical product version. Usage fields with `null` were unavailable and have not been estimated. L1 is outside the L3/L4 robustness population, so `autonomous_success` is not an L1 outcome.

The source records are the per-run metadata, hidden test results, architecture checks, and final diffs. This compact export supports inspecting outcomes and changes; operational logs and full transcripts are retained separately. See the [analysis plan](../../benchmark/config/analysis_plan.main.json) and [protocol](../../docs/protocol.md).
