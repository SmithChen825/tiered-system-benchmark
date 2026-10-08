# Current figure design and reproduction

The nine quantitative figures match Figures 8–16 installed in the thesis draft on 7 October 2026. The repository update of 9 October publishes those exact PDF/SVG/PNG assets and portable plotting scripts. The [figure map](README.md#thesis-figure-map) identifies data sources and captions.

## Design and evidence

| Figure | Form and quantity | Coverage and uncertainty |
|---|---|---|
| 8 | Overall point intervals plus task count matrix | 36 runs/system; all 48 task/system cells; descriptive Wilson 95% intervals in panel a |
| 9 | Four tier panels with system rows | 9 runs/system/tier; descriptive Wilson 95% intervals |
| 10 | Paired point intervals and direct effect/p-value columns | 12 tasks; unadjusted percentile 95% task-bootstrap intervals; Holm-adjusted tests |
| 11 | Horizontal boxes and all observations on a log-seconds axis | All 144 runs and successful subsets separated; Qwen's empty successful subset explicit |
| 12 | Functional and architectural median matrices | Three repetitions/cell; colour uses unrounded medians; labels are whole percentages |
| 13 | Direct rates and counts | 18 eligible L3/L4 runs/system; no inferential intervals |
| 14 | Within-system failure-stage composition | Failure denominators 1/3/2/36; mutually exclusive observed stages |
| 15 | Overlapping evidence-supported category counts | Same 42 failures; shared 0–36 scale; missing native trajectories marked |
| 16 | Original-to-reviewed paired points | Same 36 observations/system; counts and percentage-point changes |

The established thesis layout, palette, typography, model order and dimensions are retained. Figures are 7.1–7.2 inches wide, with PDF/SVG exports and 300 dpi PNG previews. Text remains editable in SVG; PDF fonts are embedded. The elapsed-time notes use 7.2 pt and diagnostic cell labels use 7 pt, as in the installed thesis assets; other figures have minimum text sizes of 7.5–8 pt. This synchronisation does not redesign those assets.

Wilson intervals are descriptive and do not adjust for repeated attempts within tasks. Bootstrap intervals are not simultaneous intervals corresponding to the Holm tests. Failure categories can overlap; their totals must not be interpreted as distinct failures. The L3/L4 no-response measure equals success on those tasks here and is not independent evidence of recovery. Non-significance does not establish equivalence.

## Verification of this update

Both repository plotting commands executed using Python 3.12.14, NumPy 2.3.5 and Matplotlib 3.10.8. All nine regenerated PDFs matched the installed assets' text and page dimensions. Font rasterisation differed slightly in PNG output, so the committed graphics retain the exact installed assets. Rendering metadata and font versions can affect byte or pixel identity; numerical values, labels, layout and source data are the reproduction target.

The dataset check reconciled 144 selected slots, 155 attempts and 11 exclusions. The failure-summary check reproduced aggregates for all 42 coded failures. All 11 existing analysis tests passed. Published numerical tables and experimental records remain unchanged. The plotting scripts additionally check overall/task success consistency and failure stage/category counts against their published tables.

The nine committed PDFs were rendered and visually inspected in colour and grayscale. No clipping or label overlap was observed. Direct labels and matrix values retain numerical interpretation without colour. Local review sheets are excluded from the release.

Run the two plotting commands in the [reproduction guide](README.md#reproduce) to regenerate the current set. The old standalone overall/task success figures are superseded by Figure 8; Git history retains them. Numerical-analysis manifests remain the provenance records for their original analysis runs, rather than records of this graphical refresh.
