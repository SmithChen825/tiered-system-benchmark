# Figure design and QA

The four single-plot figures answer complementary questions: overall completion level; variation across tiers; task-level concentration of failures; paired differences accounting for task grouping. They use all 144 selected observations, with reviewed scoring. The source tables also retain original scores. No observations are sampled or removed for plotting.

The Python/matplotlib workflow follows the existing Python analysis pipeline. Figures are about 180 mm wide; editable SVG and TrueType PDF are primary exports, with 600 dpi PNG previews. No raster TIFF is needed for this thesis's vector plots; the source validator's PNG-without-TIFF advisory was reviewed and accepted. No journal-specific submission compliance is claimed.

| Figure | Center / interval | Unit / coverage | QA |
|---|---|---|---|
| Overall | Proportion and descriptive 95% Wilson interval | 36 runs per system | Direct counts and names; full 0–100% axis; visual inspection passed |
| Tier | Proportion and descriptive 95% Wilson interval | 9 runs per system/tier, three tasks | Consistent colors and intervals; offsets distinguish systems; visual inspection passed |
| Task | Count k/3, fixed 0–3 scale | All 12 tasks × four systems | No clustering; all cells annotated; interval values retained in table; visual inspection passed |
| Pairwise | Rate difference and task-bootstrap percentile 95% interval | 12 paired tasks, all repetitions retained | Zero reference; effect direction explicit; exact/adjusted p values in table and caption; visual inspection passed |

Rendered PDF text checks found a minimum of 8 pt in every figure (5 pt floor). Collision audits found zero failures and zero warnings in all four PDFs. Geometry audits record single-panel status as not applicable; the task heatmap's colorbar is excluded from panel comparison. Local detailed QA diagnostics are retained separately from the curated public outputs. The source audit passed with only the reviewed TIFF advisory.

The notebook reuses the same scripts. Re-running it reproduces numerical tables; exact byte equality was checked for the tables and analysis manifest. PDF/SVG metadata may include generation times, so binary figure identity is not the numerical reproducibility criterion. Four regression tests cover Wilson boundary intervals, exact permutation extremes/ties and Holm ordering.

Reporting limits: Wilson intervals are descriptive, not clustered; pairwise bootstrap intervals are not multiplicity-adjusted; adjusted tests use six contrasts per scoring version. Small task count, three tasks per tier, post-outcome scoring review and interface differences constrain interpretation. Non-significance is not equivalence. Failure mechanisms are not inferred from success rates.

## Secondary outcomes and sensitivity

Four further figures follow the same Python/vector workflow. Elapsed time retains all individual observations and separates all-valid from successful populations. Diagnostics use task-level medians of run proportions, separately by check type. The no-response figure reports L3/L4 counts without claiming independent recovery evidence. The sensitivity figure connects original/reviewed values for the same observations.

All four figures passed visual inspection and rendered collision checks (zero failures/warnings). Minimum PDF text sizes are 6.3 pt (elapsed time), 7 pt (diagnostics), and 8 pt (no-response success and sensitivity), above the 5 pt floor. Both two-panel figures passed strict geometry alignment checks; the diagnostic colorbar is excluded from panel comparison. Source preflight has zero failures. The PNG-without-TIFF advisory is accepted for vector thesis figures; the logarithm advisory is a static-detection limitation, with every plotted duration explicitly asserted positive before plotting.

Three secondary regression tests cover empty successful populations, zero-request precision and linear quartiles. The companion notebook executed successfully and reproduced every numerical CSV byte-for-byte. The underlying 144-row dataset and earlier analysis tables were not modified. Detailed local audit files are not part of the curated publication.
