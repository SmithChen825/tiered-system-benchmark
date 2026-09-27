# L4 experiment results

36 selected observations: 3 Vue + FastAPI + PostgreSQL tasks × 4 systems × 3 repetitions. All 38 retained attempts are indexed, including two invalid attempts and their replacements. This is a descriptive evidence release; final comparative statistical analysis remains pending.

## Original and reviewed scoring

Original recorded results are preserved. `reviewed_results` applies `public-contract-audit/2026-09-26` consistently and matches the existing [144-run score review](../evaluation-review/README.md).

| System | Original successful runs | Reviewed successful runs | L4-01 reviewed | L4-02 reviewed | L4-03 reviewed |
|---|---:|---:|---:|---:|---:|
| Cursor | 6/9 | 8/9 | 3/3 | 2/3 | 3/3 |
| Devin Desktop | 6/9 | 8/9 | 3/3 | 2/3 | 3/3 |
| GPT-5.4 | 8/9 | 8/9 | 3/3 | 3/3 | 2/3 |
| Qwen2.5-Coder-7B-Instruct | 0/9 | 0/9 | 0/3 | 0/3 | 0/3 |

Success requires normal submission and every applicable functional and architecture check passing. Valid unsuccessful runs and no-progress-limit stops remain in the denominator.

L4-02 is reviewed using the same HTTP/database semantic cases for all 12 submissions. Omitted status must become active, and explicit status must satisfy the public active/inactive domain; the default is not required in a particular implementation layer. Cursor Reps 1/3 and Devin Reps 2/3 change to successful. Cursor Rep 2 and Devin Rep 1 pass the omitted-default check but remain unsuccessful because of actual explicit-input defects. Original task success is 3/12, reviewed success 7/12. The previous semantic adjustment is already included; do not apply it twice. L4-01 and L4-03 scores are unchanged. See the [uniform review and remaining coverage limitations](../../docs/evaluation-review.md).

## Files

- [selected_runs.json](selected_runs.json): 36 selected records, timing, configuration identity, available usage, original individual checks, final code diffs and separate reviewed summary results.
- [all_attempts.json](all_attempts.json): all 38 attempts, original validity/stopping fields, exclusion classification and selected replacement links.
- [Score review and reproduction](../evaluation-review/README.md): existing diagnostic evidence and offline score-mapping script. Full runtime reconstruction requires the retained research archive.

## Tasks and selection

- [L4-01 public brief](../../benchmark/tasks/L4-01/public_task_brief.md): repair downstream schema dependencies after removal of age.
- [L4-02 public brief](../../benchmark/tasks/L4-02/public_task_brief.md): restore customer creation and status behavior.
- [L4-03 public brief](../../benchmark/tasks/L4-03/public_task_brief.md): restore database connectivity and the dashboard.

Selected records occupy schedule positions 109–144, with 12 per task and 9 per system.

L4-01 Devin Rep 1 a01 was invalidated because delayed operator stopping made its completion-boundary timing invalid. Its a02 replacement is selected.

L4-03 GPT-5.4 Rep 1 a01 was stopped by the budget projection guard (`openai_projection_exceeds_stop` in the retained ledger), invalidated and replaced with a fresh a02 after authorization. The attempt index preserves the original generic infrastructure-failure message separately from this documented exclusion reason. The selected a02 is valid unsuccessful: its frontend dashboard request returned 404. It remains in the denominator; it must not be replaced by another run merely to obtain success.

## Reading the fields

`results`, `tests`, `checks` and `lifecycle_state` retain original scoring. Use `reviewed_results.success` for reviewed outcomes; original lifecycle labels may differ. Reviewed diagnostic counts do not overwrite original individual checks. Join the versioned review by `run_id`.

`reviewed_results.autonomous_success` means reviewed success without an evaluator clarification response, for these robustness-eligible tasks. Permission approvals are not clarification, and this measure does not establish recovery from every possible fault.

Timing excludes subsequent hidden evaluation and includes native permission waits. Null usage/cost values mean unavailable, not zero. All L4 `final_diff` contents are retained unchanged, including line endings; empty diffs correspond to empty archived patches. `final_diff_export` confirms that no sections were omitted. Original submissions, task packages, historical evaluators and execution freezes were not changed.

All 36 selected records passed the common evidence validator, agree with their recorded check counts and original success rule, and match the previously published reviewed score table. This does not claim exhaustive runtime coverage beyond the documented evaluators and review. In particular, the review documents the remaining duplicate-email and seed-preservation evidence limitations.

Full submission snapshots, native conversations/screenshots, sealed runtime archives, credentials and billing records remain outside this curated publication. Native transcripts are partial where full exports were unavailable; missing permission-event counts are unknown, not zero.

See the [protocol](../../docs/protocol.md), [release scope](../../docs/release-scope.md) and [analysis plan](../../benchmark/config/analysis_plan.main.json). Pilot and main observations remain separate.
