# Cursor and Devin Native-IDE Evaluation Procedure

Status: FROZEN for Cursor 3.15.6 and Devin 3.6.27  
Version: 0.2.0  
Date: 2026-08-09

## Purpose and fixed boundary

Cursor and Devin are evaluated as end-to-end commercial IDE systems. Each
uses a dedicated clean profile with isolated user-data and extension
directories. The researcher's everyday profiles, user settings, extensions,
MCP servers, rules, and project history are excluded. The product-displayed
default agent model or mode is not manually overridden.

The clean profile changes only experimental isolation: built-in product agent
features remain available. Settings sync stays off so an account login cannot
import the everyday configuration. No third-party extension may be installed
in either experiment profile. Product-managed, first-party,
application-scoped extensions that the product creates automatically are
retained, enumerated, and hash-bound; removing them would modify the native
product rather than clean the profile.

## Frozen installation observation

The 2026-08-08 machine observation was provisional. The 2026-08-09 freeze is:

| System | CLI version | Product/package version | CLI commit | Architecture | Executable file version |
|---|---|---|---|---|---|
| Cursor | 3.15.6 | 3.15.6 | `a1f686545fd0ce8917bbd2449f733551a9bce420` | x64 | 3.15.6 |
| Devin | 1.126.0 | 3.6.27 | `0becb483ee8498d49deadf6aefe8c24f58b8007e` | x64 | 3.6.27 |

Devin's CLI version (`1.126.0`) and displayed product/file version (`3.6.27`)
differ, so both are retained. Installed `product.json` names the application
`Devin`, records `Windsurf` as `oldNameShort`, and records `devin-desktop` as
the application name. The pre-pilot Windsurf observation was superseded before
any timed or scored run. The provisional machine-readable record remains
`benchmark/config/native_ide_observation.2026-08-08.json`; the controlling
record is `benchmark/config/native_ide_freeze.json`. Cursor displays
`Composer 2.5 Fast`. Devin displays `SWE-1.6 Slow` in `Devin Local`. Both
profiles use the Free account tier. Two full closes and reopens reproduced
each displayed default.

## One-time clean-profile creation

Use separate persistent directories for the two products. These directories
must remain outside every agent workspace and must never be copied into a run.

Cursor launch pattern:

```powershell
cursor.cmd --new-window --sync off `
  --user-data-dir <freeze-root>/profiles/cursor/user-data `
  --extensions-dir <freeze-root>/profiles/cursor/extensions `
  --profile "TSB Evaluation" `
  <absolute-run-workspace>
```

Devin launch pattern:

```powershell
devin-desktop.cmd --new-window --sync off `
  --user-data-dir <freeze-root>/profiles/devin/user-data `
  --extensions-dir <freeze-root>/profiles/devin/extensions `
  --profile "TSB Evaluation" `
  <absolute-run-workspace>
```

After first launch:

1. Sign in only when the product requires it for its built-in agent. Record the
   subscription/account tier label, but never an email, user ID, token, or
   credential.
2. Keep settings sync disabled. Reject import of settings, extensions, keymaps,
   rules, memories, MCP configuration, or project history.
3. Do not install extensions. Confirm the isolated extensions directory lists
   zero third-party extensions. Enumerate and hash product-managed first-party
   application-scoped extensions instead of deleting them.
4. Do not select a preferred model. Open the agent interface and record the
   model or mode that the product displays by default.
5. Close the product completely, reopen the same clean profile twice, and
   confirm that the displayed default is stable. A change must be investigated
   before freeze rather than silently averaged or selected.

## Freeze-day evidence

For each product, record:

- CLI version, commit, architecture, package version, Windows executable file
  version, executable SHA-256, and observation timestamp;
- visible version evidence (About screen when available, otherwise the native
  update-status screen plus executable metadata and hash);
- the initially displayed default agent mode and model label;
- visible agent/autonomy/terminal permission settings without changing them;
- account tier label without personally identifying information;
- clean-profile settings-file SHA-256, extensions inventory SHA-256, an empty
  third-party extension list, and a bound list of product-managed extensions;
- isolated user-data and extension directory paths;
- one configuration SHA-256 that binds the finalized record.

Populate `benchmark/config/native_ide_freeze.template.json`, change
`freeze_status` to `FROZEN`, and validate it before any pilot run. The manifest
must not contain account identifiers or absolute user-profile paths. Global
product configuration outside the isolated profile is represented by a
redacted path label, file hash, byte length, and top-level key inventory:

```powershell
python -m benchmark.runner.native_ide_freeze_validator `
  benchmark/config/native_ide_freeze.json
```

If the product updates or the displayed default changes during collection,
pause runs, record an amendment, assess affected runs, and do not mix the two
configurations silently.

## Per-run procedure

Use `benchmark.runner.native_ide_run_recorder` for the timing boundary. Run
`prepare` before opening the product, `start` at the exact task-brief submission
boundary, and `stop` immediately at a visible completion statement or frozen
wall-clock limit. The tool uses UTC anchors plus `time.monotonic_ns()`, freezes
the final workspace hash, and maintains a hash-chained timing journal under
`native_ide/`. A submitted native run records
`submission_signal=native_visible_completion` and deliberately keeps the
API-only `submit_marker_seen` field false. Duplicate starts/stops fail closed.
Full commands and required freeze/schedule arguments are in
`benchmark/runner/README.md`.

For every visible permission prompt, invoke `permission` with the verbatim
prompt, standardized type, observed decision, and observed scope. These events
always record `information_provided=false` and `counts_as_clarification=false`;
they document routine product authorization without converting it into agent
guidance. Record denied prompts as well as approved prompts.

For every agent clarification request, invoke `clarify` with the verbatim
request. Paste only the printed `response_text` back into the IDE, without any
prefix, explanation, or paraphrase. The command reuses the API wrapper's frozen
classifier: a qualifying L2-02 due-date request may receive response card
`L2-02-R1` once; all other and duplicate requests receive the fixed
no-information response. Both the canonical clarification log and a native
hash-chained journal are updated with synchronized `N_req`, `N_acc`, and
`N_resp` metadata.

1. Create a fresh run through `benchmark.runner.create_run` for the scheduled
   task, system, repetition, and attempt. The evidence directory and agent
   workspace remain separate trust zones. Confirm that the run contains the
   frozen `workspace_artifact_policy.json` snapshot and the initial
   `incidental_artifacts.json`; pilot/main creation fails while this policy is
   is not `FROZEN`, or while the complete experiment freeze manifest and its
   amendment log are not valid and sealed.
2. Confirm the workspace is at the immutable start commit and contains no
   evaluator, oracle, task specification, clarification policy, or prior-run
   state.
3. Close other windows of that product. Launch the exact clean-profile command
   above with only `workspaces/<run_id>/repo` as the opened folder. In Cursor
   3.16.29 or later, the Cursor Agents home can retain a previously selected
   repository even when a different folder is supplied on process launch.
   Before pasting the brief, explicitly select the newly opened repository in
   the Agents sidebar and visibly verify that the displayed absolute path
   contains the exact current `run_id`. A matching `storage.json` association
   alone is insufficient. If the path is truncated or ambiguous, do not start.
4. Invoke the recorder's `start` command at the exact instant the frozen task
   brief is submitted. Submit the brief verbatim; do not add debugging hints.
5. Permit autonomous inspection, editing, commands, and tests. Record every
   routine IDE permission confirmation with the recorder before continuing;
   approvals are not counted as human assistance. Do not type code, commands,
   suggestions, or diagnoses for the agent.
6. Handle every clarification through the recorder's `clarify` command. L2-02
   may receive its single pre-written response when the request qualifies.
   Every other request is logged and receives only the fixed no-information
   response.
7. Stop on an observable agent completion statement or the frozen task wall
   clock limit. At the limit, stop further agent actions and freeze the final
   workspace immediately.
8. Invoke the recorder's `stop` command, including the verbatim visible
   completion statement for submission. Record the stopping reason,
   permission events, clarification events, exported conversation, screenshots,
   and any product-provided logs or usage. Mark unavailable action/token/cost
   fields unavailable; never estimate them.
9. Close the IDE before evaluator execution. Run hidden probes and architectural
   invariants only after final-state freeze, then use the shared structured
   evaluator and finalizer.
10. Validate terminal evidence, retain the final diff and raw artifacts, and
    reset before the next independent run. For a policy-enabled run, verify
    that allowlisted untracked caches are preserved and hashed in
    `incidental_artifacts.json` but absent from `final.diff`; never clean them
    after the timer has stopped.

## Prohibited actions

- opening the researcher repository or task-package root in the evaluated IDE;
- relying only on Cursor's process launch argument when the Agents UI still
  displays a prior run repository;
- reusing the everyday profile or enabling settings sync;
- installing extensions, adding MCP servers, or adding project rules/memories;
- choosing a non-default model or mode;
- running evaluator-only tests before final-state freeze;
- giving debugging assistance outside the single frozen L2 response;
- estimating unavailable internal action counts, tokens, or cost;
- continuing agent work after submission or suspension.

## Pilot validation checklist

The procedure is ready for main-experiment freeze only after the four-system
pilot confirms that both clean profiles launch reliably, keep zero third-party
extensions, preserve their displayed defaults, operate only inside the isolated
workspace, produce exportable transcripts/evidence, obey `T_task`, and leave a
final state accepted by the common evaluator/finalizer workflow.
