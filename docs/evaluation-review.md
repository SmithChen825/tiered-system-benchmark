# Uniform evaluation review

Main collection finished on 26 September 2026 with 144 unique selected valid slots: 109 normal submissions and 35 no-progress-limit stops. All original success flags satisfy **normal submission AND every applicable functional and architectural check passing**. The finalizer regression suite passed 9/9 tests, including all-checks-pass limit stops remaining unsuccessful.

The review compared all 12 public briefs and agent-visible repository contracts with task specifications, scoring manifests, hidden tests, browser checks and probe adapters. The maintained review manifests contain 34 functional and 72 architectural scoring entries. All 144 saved prompts contain their corresponding public brief. The older evaluator source retained in this public export is historical; the [versioned review data and reproduction script](../data/evaluation-review/README.md) are the authority for the reviewed score mapping.

## Common decision rule

Requirements come from the public task contract, visible repository contracts and authorised clarification responses. An internal variable name, syntax pattern or unspecified implementation layer is not an independent requirement. Behaviourally equivalent repairs must be assessed consistently. Each supported amendment covers all 12 submissions for the task, including unsuccessful runs; it is not selected according to the benefiting system.

These decisions were made after observing submissions. Original scores remain available for sensitivity analysis. The review changes no agent execution, timing, stopping reason or validity, and does not overwrite the execution freeze.

## Evidence-supported amendments

### L2-03: actual storage behaviour

The evaluator required `PROJECT_ROOT` and `STORAGE_PATH` variables. Its temporary working-directory change also ended before HTTP requests, potentially missing delayed relative-path resolution. All 12 submission copies were tested with the application directory held active during requests, followed by reload from the project directory. Checks covered seed loading, import/export, the authoritative physical file, and rejected imports.

GPT-5.4 Rep 2 correctly anchors storage but lacks the expected variable name: architecture changes 5/6 → 6/6 and failure → success. Rep 1 remains broken with the actual application working directory: functional checks change 4/4 → 1/4 and architecture 5/6 → 4/6; it remains unsuccessful. Task success changes 5/12 → 6/12. Application reload is not evidence of Docker-volume persistence through container recreation.

### L3-01: public CORS boundary

The public brief prohibits weakening policy for unrelated origins but does not explicitly require deleting the development origin already allowed by the fixture. The researcher confirmed this interpretation: allow retention of `http://127.0.0.1:5173`, require `http://127.0.0.1:8080`, and prohibit newly allowed unrelated origins or wildcard access.

All 12 submissions received the same middleware-policy and GET/preflight checks. Cursor Reps 1–3 and GPT-5.4 Reps 1–2 change from architecture 5/7 to 7/7 and failure to success. Cursor Rep 2 uses selected attempt a02. Qwen's three submissions still fail to enable the required frontend origin and remain limit-stopped failures. Task success changes 4/12 → 9/12. The historical `stale_and_unrelated_origins_rejected` ID is retained for joining, but rejection of the existing 5173 origin is no longer required.

### L4-02: default behaviour, not implementation layer

The brief requires omitted status to default to `active`, and permits only `active` and `inactive`. It does not require the Pydantic input model to implement this default. The reviewed check uses HTTP creation, persisted status and subsequent reads. Explicit invalid values, including null, must be rejected without writing a record.

Archived HTTP/database cases from all 12 submissions support this mapping. Earlier source-pattern false negatives affected Cursor Reps 1/3 and Devin Reps 2/3: architecture 4/6 → 6/6 and failure → success. Removing the internal-model gate additionally gives Cursor Rep 2 and Devin Rep 1 the omitted-default check (4/6 → 5/6). They remain unsuccessful because Cursor accepts explicit null and Devin ignores explicit inactive and accepts invalid values. Task success is 3/12 originally and 7/12 after review; the default-layer clarification does not increase the existing intermediate 7/12 semantic result.

## All-task review and remaining limitations

Potential evaluator defects are distinguished from demonstrated run misclassifications. No automatic score reversal follows solely from a potential weakness.

| Task | Source-specific restrictions or coverage gaps | Disposition |
|---|---|---|
| L1-01 | Exact Nginx strings; file names do not establish unchanged image bytes or full layout/content | No demonstrated submitted-run false negative; retain scores |
| L1-02 | Exact 640px media query and column layout; browser also requires flex column; incomplete desktop usability checks | Equivalent grid/wrapping could be rejected; no demonstrated submitted-run reversal |
| L1-03 | Exact script attributes, path and event-listener syntax; incomplete empty-field cases | Record limitation; preserve required validation behaviour and wording |
| L2-01 | Exact handler signature/parameter name; some identity assertions use submitted ITEMS | Record potential equivalent-repair rejection and incomplete frozen-data comparison |
| L2-02 | Quote/attribute-order-dependent form parsing and broad date-literal prohibition | Optional/null/ISO rule is supported by formal response card; no observed reversal |
| L2-03 | Named-variable gate, prematurely restored cwd, no actual Compose recreation in scoring adapter | Uniform storage amendment above |
| L3-01 | Singleton origin list conflates no-wildcard with deletion of an existing origin | Uniform public-boundary amendment above |
| L3-02 | Exact Vue property/fetch/template syntax; single fixed display value | Submitted Qwen Rep 3 actually renders blank status and remains unsuccessful |
| L3-03 | Exact JSON/form/source spelling and test IDs | Retain scores; prefer request/response and UI behaviour over syntax |
| L4-01 | Direct AST annotations reject some equivalent inheritance; row count/shape do not verify every seed value | Retain scores; do not claim complete historical data preservation |
| L4-02 | Internal input-model gate, remaining AST/SQL restrictions, missing duplicate-email runtime probe | Default/status amendment above; uniqueness coverage gap remains explicit |
| L4-03 | Fixed lifespan/SQL/config syntax; limited negative connectivity and data-dependence cases | GPT Rep 1 a02 actually requests the frontend URL and gets 404; remains unsuccessful |

The review is not exhaustive fresh deployment testing of every final system. The [diagnostic export](../data/evaluation-review/diagnostic_evidence.json) supplies inspectable evidence for the three amendments; complete sealed evidence remains in the research archive.

## Reporting

The manuscript's method states this common rule. Appendix D.8 records the concrete decisions and score transitions; the conclusion does not single out a task. Planned Results reporting will compare original and reviewed system rates, diagnostic proportions and pairwise effects on the same selected slots, and state whether conclusions depend on the review. Final comparative analysis is not claimed by this supplement.
