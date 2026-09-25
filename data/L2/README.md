# L2 experiment results

36 selected observations: 3 FastAPI tasks × 4 systems × 3 repetitions.

| System | Successful runs | Success rate | L2-01 | L2-02 | L2-03 |
|---|---:|---:|---:|---:|---:|
| Cursor | 9/9 | 100% | 3/3 | 3/3 | 3/3 |
| Devin Desktop | 7/9 | 78% | 3/3 | 3/3 | 1/3 |
| GPT-5.4 | 7/9 | 78% | 3/3 | 3/3 | 1/3 |
| Qwen2.5-Coder-7B-Instruct | 0/9 | 0% | 0/3 | 0/3 | 0/3 |

Success requires normal submission and all applicable functional and architecture checks passing. Valid unsuccessful runs remain in the denominator.

## Files

- [selected_runs.json](selected_runs.json): 36 selected outcomes, task timing, configuration identity, usage when available, individual test/check results, and final code diffs.
- [all_attempts.json](all_attempts.json): all 38 attempts, including exclusions and replacement links.

## Tasks and selection

- [L2-01 public brief](../../benchmark/tasks/L2-01/public_task_brief.md)
- [L2-02 public brief](../../benchmark/tasks/L2-02/public_task_brief.md)
- [L2-03 public brief](../../benchmark/tasks/L2-03/public_task_brief.md)

Records follow frozen schedule positions 37–72. L2-02 Cursor Rep 1 a01 was excluded for an external Docker context file lock during evaluation; Devin Rep 1 a01 was an operator hotkey setup test. Their a02 replacements occupy the original slots. Analytical exclusions follow the retained post-run adjudications; original mechanical states remain in the attempt index.

## Reading the data

Task duration excludes subsequent hidden evaluation and includes native permission waits. Null usage values mean unavailable. The clarification fields preserve the recorded request/response counts. L2 is outside the L3/L4 robustness population. Results describe the configured systems on this tier.

Sources: per-run metadata, hidden test results, architecture checks, final diffs, and exclusion adjudications. See the [protocol](../../docs/protocol.md) and [analysis plan](../../benchmark/config/analysis_plan.main.json).
