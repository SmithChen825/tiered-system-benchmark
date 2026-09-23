# Release scope

This repository is a curated research-materials export prepared on 23 September 2026. It publishes the design and implementation used to prepare the main study, together with the completed pilot's descriptive tables. The `L1-experiment` branch additionally publishes 36 completed L1 main observations and an index of all 41 L1 attempts.

## Included

- L1 main results, timing, individual check outcomes, final diffs, and attempt/exclusion provenance in `data/L1/`.

- All 12 task packages, including fixtures, briefs, tests, oracle repairs, dependency files, and validation reports.
- The shared runner, evaluator, native recorder, provider adapters, required supporting modules, and focused offline tests.
- Protocol specifications, the unchanged planned 144-slot schedule, data schemas, analysis plan, and result-table definitions.
- Selected pilot data, the attempt index, descriptive summary, and selection rationale.

## Export boundary

The files were selected from the maintained research workspace. This is not a byte-for-byte historical snapshot of the original pre-main freeze: maintenance corrections made since that freeze may be present in implementation or metadata. The L1 results are exported from recorded main-experiment evidence; other tiers remain outside this data release.

Operational freeze manifests, amendment archives, account-specific authorization files, billing records, credentials, local IDE profiles, transient workspaces, and raw experiment transcripts are retained separately. As a result, source specification references to private operational records are provenance references, not a claim that the complete sealed execution environment is present here.

The `.gitattributes` file disables automatic line-ending conversion so that copied fixture bytes retain their deterministic starting commits. Do not normalize fixture line endings when editing or distributing the suite.

## Next data release

After all 144 scheduled observations are complete and verified, add the final selected-run table, attempt/exclusion provenance, analysis scripts or notebook, tables, and figures. Keep pilot and main records separate. The repository remains private until the owner chooses to publish it.
