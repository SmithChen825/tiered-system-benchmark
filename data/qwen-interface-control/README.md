# Qwen interface-control selected runs

[Selected runs](selected_runs.csv) contains one row for each of the 72 planned positions completed on 26 October 2026: 12 tasks × three repetitions × two arms. These records are separate from the main dataset. See the [results and protocol summary](../../results/qwen_interface_control.md) and thesis Appendix E.

A uses the frozen parser; B permits physical newlines inside JSON objects while preserving the other rules.

| Field | Meaning |
|---|---|
| order | Original schedule position, 1 through 72 |
| task, repetition, arm | Task identifier, repetition 1 through 3, parser condition A/B |
| run_id | Selected supplementary attempt identifier; a02 at position 51 replaces the interrupted a01 |
| validity | Evidence-validity classification |
| success | 1 for successful task completion, otherwise 0 |
| stop | Runner stop reason |
| model_responses | Number of recorded model responses |
| accepted_read_file, accepted_execute_bash | Calls accepted for dispatch, including calls that returned errors |
| successful_operations | File or command operations that returned without a tool error |
| tool_errors | Accepted operations that returned errors |
| nonempty_final_diff | 1 if the final code diff contains changes, otherwise 0 |

The export was selected from the completed run audit with its replacement mapping applied. Prechecks and the interrupted attempt are excluded. Full transcripts, local paths and operational records remain outside this export.

Run `python analysis/qwen_interface_summary.py` from the repository root to validate the 72 positions and task/repetition/arm coverage, then print totals. The script uses only Python's standard library and does not launch experiments. Accepted calls, successful operations and completed tasks are distinct outcomes.
