# Uniform evaluator review — 26 September 2026

This supplement publishes paired original and reviewed scores for **144 selected valid main observations** (12 tasks × 4 systems × 3 repetitions). All agent executions are complete; comparative analysis remains pending. Valid unsuccessful outcomes remain in the denominator.

The review is an **analysis-layer amendment made after outcomes were observed**. It does not replace the execution freeze, modify agent submissions, repeat agent executions, or change elapsed time, stopping reason, or validity. The original detailed L1/L2 exports are retained unchanged. The historical task evaluators in `benchmark/` do not automatically reproduce reviewed scores; use the declared review version below.

## Files

| File | Contents |
|---|---|
| [original_scores.json](original_scores.json) | All 144 original success flags and applicable functional/architectural check outcomes, with selected run IDs |
| [reviewed_scores.json](reviewed_scores.json) | Original/reviewed success and diagnostic counts for the same 144 slots; version `public-contract-audit/2026-09-26` |
| [diagnostic_evidence.json](diagnostic_evidence.json) | Uniform evidence for all 12 submissions in each affected task: storage, CORS and status cases |
| [selection.json](selection.json) | Selection totals, excluded-attempt index, stopping counts and original success-rule audit |
| [reproduce_scores.py](reproduce_scores.py) | Offline reconstruction and exact verification of the published reviewed table |
| `probe_storage.py`, `probe_cors.py`, `probe_status.py` | Diagnostic source used to obtain or interpret the evidence |

## Reproduce the score mapping

From the repository root, using Python 3.12 and only the standard library:

```sh
python data/evaluation-review/reproduce_scores.py
```

This checks all 144 paired rows, the normal-submission gate, uniqueness of selected slots, and coverage of every system/repetition in each corrected task. It reproduces the score mapping from published evidence; it does **not** regenerate the original executions or their complete runtime evidence.

| Task | Original success | Reviewed success | Reason |
|---|---:|---:|---|
| L2-03 | 5/12 | 6/12 | Replace variable-name requirement with storage behaviour; keep working directory active during HTTP requests |
| L3-01 | 4/12 | 9/12 | Permit the already allowed development origin; reject new unrelated origins and wildcard policies |
| L4-02 | 3/12 | 7/12 | Accept equivalent implementations and assess defaults/status validation at the HTTP/database boundary |

L4-02 already had a 7/12 intermediate semantic result. Removing the default-layer restriction changes two diagnostic counts from 4/6 to 5/6 without changing that success total. Explicit null remains invalid; omission is a different input. Other tasks retain their recorded scores. See [the review decisions and all-task limitations](../../docs/evaluation-review.md).

## Diagnostic reproduction boundaries

Use **disposable copies** of submitted repositories. Storage and status probes write test records. The two Python application probes were run with FastAPI 0.115.6 and Pydantic 2.10.4. `probe_storage.py <copy>` checks requests while holding the application working directory, then reloads from the project directory. It does not recreate Docker volumes. `probe_cors.py <copy>` examines each actual finite middleware policy and GET/preflight responses.

The L4-02 evidence was collected on 25 September in the task's PostgreSQL environment. `probe_status.py runtime` requires that running task environment and its `DATABASE_URL`. Its historical `schema` mode is retained for provenance only: **request-model defaults and validation are not independent scoring gates in this review**. The exported status evidence contains case outcomes and HTTP statuses, not the complete per-case database row archive.

Full L3/L4 submission snapshots, raw transcripts, sealed runtime logs, billing and operational records are not included. The probe source documents how evidence was obtained; regenerating it requires the retained submission archive. No credentials or model account are required for the offline score mapping.

## Use in analysis

Join by `run_id`, preserving the original and reviewed versions side by side. Use one declared version consistently across all 144 slots; do not add this review to the previous L4-02 adjustment a second time. Historical check IDs are retained for traceability even when an over-specific condition is removed. Report original-versus-reviewed sensitivity before drawing comparative conclusions. This review does not claim exhaustive dynamic validation of all final systems.
