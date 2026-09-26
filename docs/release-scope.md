# Release scope

This repository is a curated research-materials export initially prepared on 23 September 2026, extended with L2 results on 25 September, and updated on `supplement1` with the uniform evaluator review on 26 September. Main collection is complete: 144 selected valid observations. This supplement adds original/reviewed score pairs for all slots, while retaining the detailed L1/L2 exports and the completed pilot's descriptive tables.

## Included

- L1 main results, timing, individual check outcomes, final diffs, and attempt/exclusion provenance in `data/L1/`.
- L2 original results and attempt/exclusion provenance in `data/L2/`.
- All 144 selected original/reviewed score pairs, selection audit, reduced diagnostic evidence, diagnostic probe source and an offline score-reproduction script in `data/evaluation-review/`.

- All 12 task packages, including fixtures, briefs, tests, oracle repairs, dependency files, and validation reports.
- The shared runner, evaluator, native recorder, provider adapters, required supporting modules, and focused offline tests.
- Protocol specifications, the unchanged planned 144-slot schedule, data schemas, analysis plan, and result-table definitions.
- Selected pilot data, the attempt index, descriptive summary, and selection rationale.

## Export boundary

The files were selected from the maintained research workspace. This is not a byte-for-byte historical snapshot of the original pre-main freeze: maintenance corrections made since that freeze may be present in implementation or metadata. Detailed execution-level L1/L2 exports are included. L3/L4 are now represented in the score-level review, but their full submission snapshots, timing/usage tables, transcripts and runtime archives remain outside this release. Reviewed scores are a separate analysis layer, not a silent replacement of original results or historical evaluators.

Operational freeze manifests, amendment archives, account-specific authorization files, billing records, credentials, local IDE profiles, transient workspaces, and raw experiment transcripts are retained separately. As a result, source specification references to private operational records are provenance references, not a claim that the complete sealed execution environment is present here.

The `.gitattributes` file disables automatic line-ending conversion so that copied fixture bytes retain their deterministic starting commits. Do not normalize fixture line endings when editing or distributing the suite.

## Next data release

Remaining work is the complete execution-level release, final comparative analysis, original-versus-reviewed sensitivity, tables and figures. The included offline script reproduces score mapping from exported evidence; it does not reproduce agent executions or replace the planned statistical analysis. Keep pilot and main records separate.

## L2 experiment addition

The earlier L2-experiment addition contains 36 selected L2 main observations and all 38 attempts, including two documented exclusions and replacements. Its original result files are preserved. The `supplement1` review adds the L2-03 scoring amendment and score-level L3/L4 coverage; see the [review guide](../data/evaluation-review/README.md).
