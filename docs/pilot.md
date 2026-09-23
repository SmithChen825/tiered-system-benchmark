# Pilot study

The pilot was closed out in August 2026 to validate the experiment before the 144-run main collection. It covered one representative task per tier and four systems: **16 selected task–system observations**.

| Evidence | Count |
|---|---:|
| Selected valid terminal observations | 16 |
| Successful / unsuccessful | 7 / 9 |
| Retained attempt records | 27 |
| Selected records passing common validation | 16 / 16 |
| Selected native records passing native validation | 8 / 8 |

## Data files

- [selected_runs.csv](../data/pilot/selected_runs.csv): the 16 selected records, with outcomes, stopping reasons, elapsed time, diagnostic checks, and available interface-specific measures.
- [all_attempts.csv](../data/pilot/all_attempts.csv): the 27-attempt index, including retained non-selected attempts.
- [summary.json](../data/pilot/summary.json): the original descriptive review summary.
- [selection record](../benchmark/config/pilot_selected_attempts.json): selected identifiers and replacement explanations.

Blank interface-specific CSV cells mean unavailable or inapplicable, not zero. Original `evidence_path` and hash columns identify records in the private research archive; raw transcripts, screenshots, and account records are not bundled in this release.

## What changed before the main experiment

All four selected GPT-5.4 pilot runs used the provisional 15-action allowance. Three stopped at the action limit; one of those had a repaired final state but no valid submission. The common API allowance was therefore raised to **30 actions** for both API systems before main collection.

The 5,400-second task limit, 180-second command timeout, three-response no-progress limit, 100,000-character context boundary, and sandbox restrictions were retained. No selected run reached either time limit, and the context boundary was not stress-tested.

With one observation per task–system cell, this pilot validates process feasibility. It does not support a leaderboard, stable comparative success estimates, or inferential claims. Pilot records are excluded from the 144-run main analysis.
