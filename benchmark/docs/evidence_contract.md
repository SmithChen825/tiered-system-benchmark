# TSB Run and Evidence Contract

Status: implementation draft  
Version: 0.1.0  
Date: 2026-08-08

This contract defines the shared, provider-independent run layout used by the
Tiered System Benchmark (TSB). It does not configure or call an evaluated API.
It may be revised during the representative pilot and must be frozen before the
main experiment.

## 1. Directory boundary

The researcher repository, agent workspace, and evidence directory are three
different trust zones:

```text
benchmark/tasks/<task_id>/       researcher-only task package
workspaces/<run_id>/repo/        agent-visible working copy
runs/<run_id>/                   evaluator-owned evidence
```

An evaluated system receives access only to `workspaces/<run_id>/repo/` and the
frozen public task brief. It must not receive the repository root or the
evidence directory as its working directory.

The workspace is copied only from `fixture_repo/`. It must not contain:

- `evaluator/`;
- `oracle/`;
- `task_spec.json`;
- `fixture_manifest.json`;
- `clarification_policy.json`;
- `validation_report.md`.

The evaluator reads the final workspace only after submission or suspension.
Hidden tests, architecture checks, the oracle, and clarification policy remain
outside the agent-visible filesystem boundary. Container execution must apply
the same boundary by mounting or copying only the run workspace.

## 2. Run identifier

The canonical identifier is:

```text
<phase>-<task_id>-<system_slug>-r<repetition>-a<attempt>
```

Example:

```text
pilot-L3-01-gpt-5-4-r01-a01
```

- `phase` is `validation`, `pilot`, or `main`.
- `task_id` uses the frozen `L<tier>-<two digits>` format.
- `system_slug` is lowercase ASCII with hyphens.
- `repetition` is the scheduled independent repetition, zero-padded to two
  digits.
- `attempt` is normally `01`. Only a formally invalid run is repeated with a
  new attempt number. A valid unsuccessful run is not repeated.

The identifier is deterministic and does not contain a timestamp. Timestamps
remain explicit metadata fields, so reruns and ordering are not inferred from a
filename.

## 3. Lifecycle

```text
prepared -> running -> submitted  -> evaluating -> successful | unsuccessful
                    -> suspended  -> evaluating -> unsuccessful

prepared | running -> invalidated
```

`submitted` and `suspended` are stopping transitions retained through
`stopping.reason`. The final `lifecycle_state` is `successful`, `unsuccessful`,
or `invalidated` after evaluation.

- Submission freezes the final workspace before evaluator-only checks.
- A task wall-clock, API action, or command-timeout limit causes suspension,
  freezes the final workspace, and remains a valid unsuccessful outcome.
- `invalidated` is reserved for evaluator mistakes, runner failures, or
  infrastructure failures outside the assigned fault that prevent the promised
  brief or environment from being delivered.
- Agent-caused tool errors, service failures, timeouts, and unsuccessful repairs
  are valid unsuccessful outcomes.
- The environment is reset only before a new independent run, never during a
  run.

## 4. Evidence directory

Every run directory contains the same filenames. A file that is unavailable,
not yet produced, or not applicable records that state explicitly rather than
being silently omitted.

```text
runs/<run_id>/
  metadata.json
  task_prompt.txt
  transcript.txt
  raw_model_response.jsonl
  adapter_decisions.jsonl
  clarification_log.json
  hidden_test_results.json
  architecture_checks.json
  docker_status.txt
  docker_logs.txt
  database_checks.json
  final.diff
```

Runs prepared under the prospective incidental-workspace-artifact policy also
contain `workspace_artifact_policy.json` and `incidental_artifacts.json`.
The former is the run-local policy snapshot. The latter is an evaluator-owned
inventory of allowlisted untracked caches retained in the frozen workspace but
excluded from `final.diff`. Historical frozen runs without these files remain
valid under their original evidence contract and are not backfilled.

Cursor/Devin runs additionally create evaluator-owned files beneath
`native_ide/`: `run_record.json`, `timing_events.jsonl`,
`permission_events.jsonl`, and `clarification_events.jsonl`. The three journals
are append-ordered and SHA-256 hash-chained; their permission/clarification
chain heads are bound into the native run record. These files are never copied
into the evaluated workspace.

Provider-specific raw payloads may be added under `provider/`, but the common
files and metadata remain provider-independent. Commercial-IDE values that are
not exposed are recorded as `unavailable`, never estimated.

Every API `model_response` line retains the complete raw provider payload and
the normalized view used by the runner. The normalized view includes
`normalization_metadata`. Qwen's reviewed format-compatibility candidate writes
an explicit applied/rejected decision and reason there; an applied conversion
also records the source-content hash and flags that its call ID was synthetic
and that no semantic repair occurred. Evidence validators preserve these
fields rather than rewriting the raw response into the normalized form.

## 5. Evidence-writing authority

- The preparation layer creates the run ID, workspace, prompt copy, fixture
  hash, initial metadata, and explicit placeholders.
- The evaluated system changes only its workspace.
- The wrapper or native-IDE recorder appends observable interaction evidence.
- The evaluator freezes the final state, runs hidden checks, records results,
  generates the final diff, and finalizes metadata.
- The evidence validator is read-only. It reports missing, malformed, or
  inconsistent evidence and does not repair a run automatically.

## 6. Hashes

The preparation layer verifies the copied workspace against the frozen
`aggregate_fixture_hash` in the task's `fixture_manifest.json`, initializes a
deterministic Git repository, and verifies its immutable `start_commit`. The
commit uses a fixed author, timestamp, message convention, branch, line-ending
policy, and file-mode policy. The layer also records the SHA-256 of the exact
public prompt bytes. Configuration hashes remain nullable during researcher
validation, but must be frozen before a pilot or main run starts.

## 7. Current integration scope

The initial integration covers `L1-01`, `L2-02`, `L3-01`, and `L4-01`. It
creates isolated workspaces and standardized evidence without OpenAI, Hugging
Face, Cursor, or Devin configuration. Provider adapters will consume this
contract later.
