# TSB Run Metadata Data Dictionary

Status: implementation draft  
Schema: `benchmark/schemas/run_metadata.schema.json`  
Date: 2026-08-08

The analysis unit is one attempted run. Valid and invalidated attempts are both
retained. The schema is intentionally provider-independent.

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Metadata contract version. Currently `1.0.0`. |
| `run_id` | string | Canonical phase/task/system/repetition/attempt identifier. |
| `phase` | enum | `validation`, `pilot`, or `main`. |
| `lifecycle_state` | enum | Current or terminal FSM state. |
| `validity_status` | enum | `pending`, `valid`, or `invalid`. |
| `task.task_id` | string | Frozen task identifier, for example `L3-01`. |
| `task.tier` | integer | Architectural tier, 1 through 4. |
| `task.repetition` | integer | Independent scheduled repetition. |
| `task.attempt` | integer | Attempt number; greater than 1 only for formal invalid reruns. |
| `task.fixture_sha256` | string | Frozen aggregate hash of the faulty fixture. |
| `task.prompt_sha256` | string | SHA-256 of the exact frozen task-prompt bytes. |
| `task.start_commit` | string | Deterministic immutable Git commit for the copied faulty fixture. |
| `task.clarification_opportunity` | boolean | Whether this is the single frozen opportunity task. |
| `system.system_id` | enum | Evaluated system or researcher validation actor. |
| `system.system_slug` | string | Filesystem-safe system component used in `run_id`. |
| `system.evaluation_interface` | enum | `native_ide`, `api_wrapper`, or `researcher_validation`. |
| `system.product_version` | string/null | Commercial product/wrapper version. |
| `system.model_identifier` | string/null | Displayed default or pinned model identifier. |
| `system.provider_endpoint` | string/null | Provider endpoint identifier where applicable. |
| `system.configuration_sha256` | string/null | Hash of the frozen system configuration. |
| `schedule.order_position` | integer/null | Seeded position 1--4 inside the task-repetition block. |
| `schedule.random_seed` | string/null | Frozen schedule seed. |
| `timing.started_at` | date-time/null | UTC task-prompt submission time. |
| `timing.ended_at` | date-time/null | UTC submission/suspension time after final-state freeze. |
| `timing.elapsed_seconds` | number/null | End-to-end elapsed seconds; native/API runners preserve their recorded monotonic duration through finalization when timestamps are not overridden. |
| `limits.task_wall_clock_seconds` | integer/null | Common frozen task-level limit. |
| `limits.api_action_limit` | integer/null | API-wrapper limit; not applicable to native IDEs. |
| `limits.command_timeout_seconds` | integer/null | Per-command API-wrapper timeout. |
| `stopping.reason` | enum/null | Submission, applicable limit, or formal invalidation cause. |
| `stopping.detail` | string/null | Short factual detail; not an inferred failure explanation. |
| `stopping.submission_signal` | enum/null | `api_submit_marker`, `native_visible_completion`, or null when no evaluated-agent submission signal applies. |
| `stopping.submit_marker_seen` | boolean | Whether the API-only `<SUBMIT_FIX>` marker was actually observed; false for native-IDE completion. |
| `results.success` | boolean/null | Primary outcome for a valid evaluated run. |
| `results.functional_tests` | object | Passed/applicable counts and their proportion (`C_func`). |
| `results.architecture_checks` | object | Passed/applicable counts and their proportion (`C_arch`). |
| `results.robustness_eligible` | boolean | True only for Level 3 and Level 4 evaluated runs. |
| `results.autonomous_success` | boolean/null | Eligible success without an evaluator response. |
| `clarification.opportunity` | boolean | Must match the task specification. |
| `clarification.requests` | integer | `N_req`. |
| `clarification.authorized_requests` | integer | `N_acc`. |
| `clarification.responses` | integer | `N_resp`. |
| `usage.status` | enum | `available`, `unavailable`, or `not_applicable`. |
| `usage.input_tokens` | integer/null | Provider-reported input tokens only. |
| `usage.output_tokens` | integer/null | Provider-reported output tokens only. |
| `usage.total_tokens` | integer/null | Provider-reported total tokens only. |
| `usage.monetary_cost` | number/null | Recorded cost using the frozen pricing basis. |
| `usage.currency` | string/null | ISO-style currency code, normally `USD`. |
| `artifacts.*` | relative path | Canonical evidence filenames beneath the run directory. |

### Raw model-response normalization audit

`raw_model_response.jsonl` is an artifact rather than a field in
`metadata.json`. Each `model_response` record preserves the provider's raw
payload and a normalized view. The normalized view includes
`normalization_metadata`. For Qwen, its `compatibility_normalizer` object
records `id`, `applied`, and `reason`; applied conversions additionally record
`source_content_sha256`, `tool_name`, `synthetic_call_id`, and
`semantic_repair_performed`. This permits separate counts of native calls,
format-only converted calls, and responses rejected by the compatibility
boundary without changing the primary run-level success outcome.

## Missingness rules

- `null` means a value has not yet been produced or is structurally inapplicable; the frozen fixture hash and start commit are never nullable.
- `unavailable` means the evaluated product does not expose the value.
- `not_applicable` means the field does not apply to the evaluation interface.
- Unavailable commercial-IDE usage and cost values are never estimated.
- Final success is never populated for an invalidated run.
- Native IDE timing additionally retains UTC anchors, monotonic nanoseconds,
  wall-clock elapsed time, wall-minus-monotonic difference, final workspace
  hash, and a hash-chained transition journal in `native_ide/`. The shared
  `timing.elapsed_seconds` value is the monotonic duration.
- Native permission evidence records the verbatim prompt, standardized prompt
  type, approved/denied decision, decision scope, and fixed non-information
  flags in `native_ide/permission_events.jsonl`.
- Native clarification evidence records the verbatim request, authorization,
  reason code, delivered frozen text, and response-card ID in a hash-chained
  journal while retaining the common `clarification_log.json` event shape and
  synchronized `N_req`, `N_acc`, and `N_resp` counts.

## Derived analysis fields

The frozen analysis notebook may derive success rates, Wilson intervals, risk
differences, clarification rates, robustness, and elapsed-time summaries. These
aggregates must not be written back as alternative weighted run scores.
