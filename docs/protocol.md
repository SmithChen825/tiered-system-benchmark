# Experimental protocol

## Research questions

1. How does success change across four architectural tiers?
2. Do systems ask for clarification when a required business rule is missing, and avoid unnecessary requests on complete briefs?
3. How do the four configured systems differ in success, elapsed time, clarification, and autonomous recovery?

## Design

There are three tasks per tier, four systems, and three fresh repetitions per task–system pair. Pilot runs are separate. Within each task–repetition block, a seeded permutation orders the four systems. The [144-slot schedule](../benchmark/config/run_schedule.main.json) contains planned run identifiers, not experiment results.

Cursor and Devin use their native IDE workflows. GPT-5.4 and Qwen use a shared API wrapper with the same logical action space. Each run starts from the task's deterministic Git commit and reset environment. Evaluator-only tests assess the frozen final state after submission or suspension.

## Frozen execution limits

| Control | Main-experiment setting |
|---|---:|
| Task wall clock, all systems | 5,400 seconds |
| Accepted API actions | 30 |
| API command timeout | 180 seconds |
| Consecutive non-acting API responses | 3 |
| Retained API interaction context | 100,000 characters |

The API sandbox disables external network access and host-Docker control. The evaluator operates the separate integration environment. Native permission events are recorded independently of API actions; these quantities are not interchangeable.

## Clarification

Only L2-02 deliberately omits one essential non-technical requirement. A qualifying request receives its fixed response card. Other briefs are complete. Permission approvals are not clarification, and technical faults do not justify debugging assistance.

## Outcomes and analysis

A successful run must submit normally and pass every applicable functional check and architectural invariant. Valid execution-limit stops are unsuccessful even if final checks pass. Invalid infrastructure attempts remain in the audit trail and are excluded from performance denominators; an eligible fresh replacement fills the scheduled slot.

Report binary success, functional and architectural diagnostic proportions, successful-run completion times, all-valid-run stopping times, clarification measures, and autonomous recovery separately. There is no weighted aggregate score.

The planned analysis uses descriptive Wilson intervals, task-level bootstrap risk differences, exact paired task-label-swap tests with Holm adjustment, and median/IQR timing summaries. All comparative inference is exploratory. The task, rather than an individual repetition, is the resampling unit. See the [machine-readable analysis plan](../benchmark/config/analysis_plan.main.json) and [data dictionary](../benchmark/docs/run_data_dictionary.md).
