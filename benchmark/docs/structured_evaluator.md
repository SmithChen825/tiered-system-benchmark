# Structured Evaluator Runner and Finalizer

Status: common runner/finalizer and four representative task adapters implemented  
Version: 0.1.0  
Date: 2026-08-08

## Responsibility split

The evaluator has three layers:

1. Task-specific probe adapters execute frozen pytest, browser, Compose,
   database, and operational probes against a frozen final workspace and emit
   source observations.
2. The provider-independent structured runner verifies source coverage against
   the approved manifest, derives functional and architectural results, binds
   the workspace hash, and emits one structured result bundle.
3. The provider-independent finalizer verifies the bundle against the approved
   `evaluator_manifest.json`, generates `final.diff`, computes `C_func` and
   `C_arch`, writes common evidence files, and performs the terminal metadata
   transition.

Task-specific code must not write `metadata.json` or decide the final run
status. The finalizer must not reinterpret a failed agent service as evaluator
infrastructure failure.

## Two-stage CLI

The structured runner consumes the task adapters' source observations:

```powershell
python -m benchmark.runner.structured_evaluator `
  runs/<run_id> `
  workspaces/<run_id>/repo `
  observations.json `
  result_bundle.json
```

The finalizer then seals common evidence and terminal metadata:

```powershell
python -m benchmark.runner.evaluator_finalizer `
  runs/<run_id> `
  workspaces/<run_id>/repo `
  result_bundle.json `
  --stop-reason submitted `
  --started-at 2026-08-08T00:00:00Z `
  --ended-at 2026-08-08T00:10:00Z
```

The observation schema is
`benchmark/schemas/evaluation_observations.schema.json`. Every functional test
ID, every architecture evidence `source_id`, and every operational evidence ID
must occur exactly once when evaluation succeeds. Extra and missing IDs are
rejected. Architecture checks pass only when all their applicable sources pass.

The common runner/finalizer and L1-01, L2-02, L3-01, and L4-01 probe adapters
are implemented. Their baseline/oracle full-cycle results are recorded in
`benchmark/docs/probe_adapter_validation.md`.

## Result bundle

The sealed bundle schema is
`benchmark/schemas/evaluation_result_bundle.schema.json`. It contains:

- the run and task identifiers;
- the exact final-workspace SHA-256;
- one result for every approved functional-test ID;
- one result for every approved architecture-check ID;
- one result for every operational-evidence ID;
- Docker, database, and evaluator diagnostic evidence;
- an optional formal evaluator/infrastructure error.

When there is no formal evaluation error, the result IDs must exactly match the
approved manifest: no missing, duplicate, or extra results are accepted. A
failed service, HTTP error, browser failure, or assertion caused by the final
agent state is represented as a failed check, not as `evaluation_error`.

## Terminal decision

- `successful`: every applicable functional test and architecture check passes,
  and the run ended by normal submission.
- `unsuccessful`: at least one applicable check fails, or the run ended at a
  frozen execution limit.
- `invalidated`: the result bundle records an evaluator error or infrastructure
  failure outside the assigned fault that prevented valid final-state
  assessment.

`C_func` and `C_arch` are computed independently as passed/applicable. They are
never combined. Operational evidence is retained but is not scored.

## Final-state binding

The result bundle records a workspace hash computed with the task's frozen
fixture-hash exclusions. The finalizer recomputes this value before accepting
the bundle. It also generates `final.diff` against the deterministic Git start
commit using a temporary Git index, so tracked changes, deletions, and
non-incidental untracked files are captured without modifying the agent's
index. For runs prepared with `workspace_artifact_policy.json`, allowlisted
untracked runtime caches are preserved in the frozen workspace and recorded by
path, size, classification, and SHA-256 in `incidental_artifacts.json`, but are
not added to `final.diff`. Tracked changes and nonmatching untracked files are
never exempt. See `benchmark/docs/workspace_artifact_policy.md`.

## Crash behaviour

The finalizer first records `evaluating`, then writes structured artifacts, and
only then writes a terminal state. A crash therefore leaves an explicit
non-terminal record that can be inspected and rerun; it cannot silently appear
as a completed evaluation. If terminal evidence validation fails, the finalizer
returns metadata to `evaluating` while preserving artifacts for diagnosis.
