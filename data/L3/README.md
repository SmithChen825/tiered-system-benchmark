# L3 experiment results

36 selected observations: 3 Vue + FastAPI tasks × 4 systems × 3 repetitions. All 38 retained attempts are indexed, including two excluded attempts and their replacements. This is a descriptive evidence release; final comparative statistical analysis remains pending.

## Original and reviewed scoring

The original recorded results are preserved. `reviewed_results` applies `public-contract-audit/2026-09-26` consistently to every selected observation and matches the previously published [144-run score review](../evaluation-review/README.md).

| System | Original successful runs | Reviewed successful runs | L3-01 reviewed | L3-02 reviewed | L3-03 reviewed |
|---|---:|---:|---:|---:|---:|
| Cursor | 6/9 | 9/9 | 3/3 | 3/3 | 3/3 |
| Devin Desktop | 9/9 | 9/9 | 3/3 | 3/3 | 3/3 |
| GPT-5.4 | 7/9 | 9/9 | 3/3 | 3/3 | 3/3 |
| Qwen2.5-Coder-7B-Instruct | 0/9 | 0/9 | 0/3 | 0/3 | 0/3 |

Success requires normal submission and all applicable functional and architecture checks passing. Valid unsuccessful runs remain in the denominator. L3-01's reviewed CORS boundary permits the pre-existing development origin 127.0.0.1:5173, requires 127.0.0.1:8080, and prohibits newly allowed unrelated origins or wildcards. Cursor Reps 1–3 and GPT-5.4 Reps 1–2 change from unsuccessful to successful; all 12 L3-01 submissions received the same review. See the [decision and evidence](../../docs/evaluation-review.md). L3-02 and L3-03 scores are unchanged.

## Files

- [selected_runs.json](selected_runs.json): 36 selected observations, timing, configuration identity, available usage, original individual checks, curated final code diffs, and explicitly separate reviewed summary results.
- [all_attempts.json](all_attempts.json): all 38 attempts, recorded versus analytical validity, exclusion reasons and selected replacement links.
- [Original/reviewed score mapping and reproduction](../evaluation-review/README.md): versioned review, check-level diagnostic evidence and the offline reproduction script already present in this repository.

## Tasks and selection

- [L3-01 public brief](../../benchmark/tasks/L3-01/public_task_brief.md): CORS policy repair.
- [L3-02 public brief](../../benchmark/tasks/L3-02/public_task_brief.md): frontend/API order-status contract.
- [L3-03 public brief](../../benchmark/tasks/L3-03/public_task_brief.md): password-reset API version migration.

Selected records follow frozen schedule positions 73–108, with 12 observations per task and 9 per system. L3-01 Cursor Rep 2 a01 was an operator hotkey setup test, analytically excluded; its sealed mechanical record remains pending/submitted. L3-02 Devin Rep 3 a01 was invalidated for a workspace mismatch. Their a02 replacements occupy the original slots. In particular, L3-02 Devin Rep 3 a02 is selected, not a01. Invalid attempts do not become valid failures or additional observations.

## Field meanings and limits

`results`, `tests`, `checks` and `lifecycle_state` preserve original recorded scoring. Use `reviewed_results.success` for reviewed binary outcomes; the original lifecycle label can therefore differ from reviewed success. Reviewed diagnostic counts do not overwrite the original individual checks. Join the review evidence by `run_id`; do not apply corrections twice. Historical check IDs remain traceability identifiers rather than a new requirement to remove the development origin.

`reviewed_results.autonomous_success` means reviewed success without an evaluator clarification response, for these robustness-eligible L3 tasks. The original value remains in `results`. Neither field counts IDE permission approvals as clarification or demonstrates recovery from every possible fault.

Timing excludes subsequent hidden evaluation and includes native permission waits. Null usage or cost values mean unavailable, not zero. `final_diff` preserves the retained UTF-8 patch sections and their line endings. For L3-01 GPT-5.4 Rep 1 only, 451 incidental `.venv/` dependency file sections are omitted; its backend repair is retained. `final_diff_export` records this curation per run. All other archived diffs are included unchanged; empty diffs in this export correspond to empty archived diffs. The complete original patch remains in the research archive. Configuration identifiers document the recorded setup. The source task packages and historical evaluators were not changed by this publication.

The export was checked against each selected run's metadata, check results and common evidence validator, and against the existing 144-run reviewed table. Raw transcripts, billing, credentials, local account settings, full submission snapshots and sealed runtime archives remain outside this curated release. Native transcripts are partial where full exports were unavailable; L3-03 Cursor Rep 3 lacks its completion screenshot in the archive. These limitations must not be interpreted as zero permission events or complete native conversation evidence.

See the [protocol](../../docs/protocol.md), [release scope](../../docs/release-scope.md) and [analysis plan](../../benchmark/config/analysis_plan.main.json). Pilot records are separate from the main observations.
