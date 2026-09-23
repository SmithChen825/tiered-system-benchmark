# Shared API-Agent Wrapper Core

Status: core, sandboxed tools, both mock transports, cross-provider symmetry,
full mock-adapter runner/evidence integration, and offline-tested live HTTPS
bridges implemented; paid live smoke tests pending  
Version: 0.8.0  
Date: 2026-08-09

## Scope

The shared core in `benchmark/runner/api_wrapper/` runs both API-evaluated
systems through the same observable control loop. It does not import an OpenAI
or Hugging Face SDK and does not read credentials. Provider adapters must
normalize one response into `ModelTurn`; logical tool executors must return
`ToolExecutionResult`.

The core owns:

- conversation context and deterministic complete-turn pruning;
- model-turn sequencing;
- exact `<SUBMIT_FIX>` detection;
- accepted-action counting;
- task-wall-clock, API-action, and command-timeout stopping transitions;
- usage aggregation when every provider turn exposes usage;
- raw response, normalized decision, transcript, and clarification evidence;
- exception classification and metadata lifecycle updates.

The evaluator remains separate. The wrapper ends at `submitted`, `suspended`,
or formal `invalidated`; it never assigns task success.

## Sandboxed logical tools

`SandboxedLogicalToolExecutor` implements the four shared logical actions. It
must be created with `for_task(task_id)` so the single evaluator-side
clarification policy is selected without copying that policy into the run
workspace.

- `read_file` accepts one canonical relative path, reads UTF-8 regular files,
  rejects absolute paths, traversal, Windows alternate-data-stream syntax,
  `.git`, and every symbolic-link component, and truncates output at 256 KiB.
- `patch_file` accepts a standard unified git diff. It preflights with
  `git apply --check`, limits a call to 1 MiB and 64 files, and rejects paths
  outside the workspace, Git metadata, binary patches, rename/copy operations,
  symlink modes, and submodule modes.
- `execute_bash` delegates only to `DockerCommandSandbox`. The frozen default
  image is addressed by digest. The container receives one writable bind mount
  for the run workspace and a nested read-only mount for `.git`; its root
  filesystem is read-only, its network is disabled, no Docker socket is
  mounted, all Linux capabilities are dropped, privilege escalation is
  disabled, and memory, CPU, PID, output, and time are bounded. A command's
  non-zero exit is observable and non-terminal; a frozen timeout raises the
  existing valid-suspension transition.
- `request_human_clarification` loads the researcher-only response card outside
  the workspace. Complete-brief tasks always receive the no-information
  response. L2-02 requests are classified against the frozen due-date rubric,
  and at most one information-bearing response is issued per workspace.

The default command sandbox intentionally has neither network access nor the
host Docker socket. Task-specific command images may contain frozen test
dependencies, but giving an evaluated command access to the host Docker daemon
is outside this trust boundary. Compose/browser/database assessment remains in
the post-run evaluator probes.

Example construction:

```python
from benchmark.runner.api_wrapper import SandboxedLogicalToolExecutor

executor = SandboxedLogicalToolExecutor.for_task("L2-02")
```

## Normalized transport contract

A provider transport receives the current tuple of `ContextMessage` values and
the four frozen logical tool definitions. It returns one `ModelTurn` containing:

- observable assistant text;
- zero or more `ToolCall` values with unique call IDs;
- the raw provider payload;
- provider response ID where available;
- usage for that turn where available.

Provider retries that never reach the logical tool executor remain transport
events and do not increment the API action count. An exhausted provider failure
is an infrastructure invalidation, not an unsuccessful repair.

The frozen request/response, usage, tool-call, retry, and error taxonomy is in
`benchmark/docs/provider_transport_contract.md`. The GPT-5.4 Responses and
Qwen/vLLM Chat Completions adapters are both implemented with injected
requesters, so their wire payloads and raw-response normalization can be tested
without provider SDKs, network calls, Endpoint URLs, or API credentials.
The real standard-library HTTPS requesters are isolated in
`benchmark/runner/api_wrapper/transports/live_http.py`; their explicit
credential/cost authorization boundary and offline verification are documented
in `benchmark/docs/live_provider_bridges.md`.

## Run-loop rules

1. A prepared `api_wrapper` run becomes `running`, records `started_at`, and
   initializes live evidence files.
2. The transport receives the system prompt, frozen task brief, and retained
   complete model/tool turn groups.
3. Raw and normalized response evidence is written before any tool executes.
4. A task wall-clock limit has priority if it is reached while awaiting the
   response.
5. An exact `<SUBMIT_FIX>` in assistant text causes submission. Tool calls in
   that same response are recorded but ignored. Submission is not an action.
6. Otherwise, allowed tool calls execute in response order. Each call reaching
   the executor increments the action count once; multiple calls in one model
   response count separately.
7. Unknown tool names return an observable error to the model without reaching
   the executor and without incrementing the action count.
8. Reaching the action limit before another accepted call causes
   `api_action_limit` suspension. `ToolCommandTimeout` causes
   `command_timeout` suspension.
9. Tool results are appended to the same complete turn group before the next
   transport request.

## Context management

The system prompt and frozen task brief are immutable prefix messages. Each
assistant response and all of its tool results form one complete group. When a
frozen character limit is configured, only the oldest complete groups are
removed; an assistant tool call is never retained without its result or vice
versa. A deterministic context notice reports how many groups were removed.

The character limit remains optional during implementation. Its final value,
along with provider context/token settings, must be frozen before the pilot.

## Exception boundary

| Condition | Wrapper outcome |
|---|---|
| Agent command exits non-zero | Observable tool error; run continues |
| Frozen command timeout | Valid `suspended`, reason `command_timeout` |
| API action limit | Valid `suspended`, reason `api_action_limit` |
| Task wall-clock limit | Valid `suspended`, reason `task_wall_clock_limit` |
| Provider unavailable after transport retries | `invalidated`, reason `infrastructure_failure` |
| Shared tool infrastructure unavailable | `invalidated`, reason `infrastructure_failure` |
| Malformed normalized response or wrapper/executor bug | `invalidated`, reason `runner_error` |

Configuration errors detected before start leave the run in `prepared`, so a
researcher can correct the freeze metadata without consuming an attempt.

## Evidence

- `raw_model_response.jsonl`: raw payload plus the normalized response view;
- `adapter_decisions.jsonl`: context snapshots, accepted/rejected calls,
  stopping decisions, and exception classification;
- `transcript.txt`: observable task, assistant text, tool calls, and results;
- `clarification_log.json`: request, decision, and response events;
- `metadata.json`: lifecycle, timing, stopping reason, clarification counts,
  and complete usage when available.

No private chain-of-thought is requested or recorded.

For Qwen, each normalized response also records
`normalized.normalization_metadata.compatibility_normalizer`. The record
contains an `applied` boolean and a stable reason. When the narrowly reviewed
fenced-JSON compatibility path applies, it additionally records the raw
content SHA-256, tool name, synthetic-call-ID flag, and
`semantic_repair_performed=false`. The raw payload remains unchanged, so the
original provider formatting is always independently auditable.

## Current verification

Mock-transport integration tests cover submission precedence, multi-call action
counting, exact action-limit enforcement, command and wall-clock suspension,
unknown-tool rejection, provider failure, executor failure, clarification
counts, usage aggregation, and complete-turn context pruning. Tool security
tests cover traversal, absolute paths, UTF-8 handling, symlink rejection where
the host permits link creation, Git metadata, unsafe patch modes, malformed and
oversized patches, output limits, timeout propagation, clarification response
limits, and Docker hardening flags. A real Docker smoke test also verified
normal workspace writes, read-only `.git`, disabled networking, timeout cleanup,
and zero leftover tool containers. Every wrapper-produced submitted, suspended,
or invalidated record passes the common evidence validator.

GPT-5.4 mock-transport tests additionally cover the frozen snapshot and request
settings, strict function schemas, manual `function_call` /
`function_call_output` history, ordered text and multiple tool calls, malformed
argument JSON, detailed usage, refusal/incomplete finish mapping, deterministic
retry audit, and the infrastructure-versus-contract-error boundary. The full
Qwen/vLLM tests cover the exact model ID, Chat Completions history, strict tool
envelopes, ordered parallel calls, malformed arguments, provider-native usage,
finish reasons, retry/error evidence, and normalized symmetry with the GPT
adapter. A separate cross-provider suite projects the different wire histories
and tool envelopes into their common semantics, compares normalized calls and
all usage details, checks equivalent finish reasons, exercises eight retryable
HTTP conditions and six terminal conditions, and verifies that malformed
provider shapes remain contract errors for both adapters.

The provider-runner integration suite uses the actual GPT and Qwen mock
adapters, `ApiAgentRunner`, `SandboxedLogicalToolExecutor`, isolated run
creation, and the common evidence validator. For each provider it verifies a
two-turn lifecycle containing an ordered successful file read, a malformed
counted tool call with an observable error, linked tool-result history, exact
submission, usage aggregation, raw and normalized evidence, transcript output,
and terminal metadata. It also drives three retryable 503 responses through
each adapter and confirms that the exhausted attempt audit becomes a retained
`infrastructure_failure` invalidation without consuming an action.

The credential-free representative-task dry run then exercised the complete
runtime and evaluator lifecycle on 2026-08-08. L1-01/GPT, L2-02/Qwen,
L3-01/GPT, and L4-01/Qwen all reached `successful`; their `C_func/C_arch`
results were respectively `2/2, 6/6`, `7/7, 6/6`, `4/4, 7/7`, and `2/2,
8/8`. L2 recorded exactly one authorised request and one frozen response. All
four workspaces excluded researcher-only paths, all submitted and terminal
records passed the common validator, and probe cleanup left no TSB containers,
volumes, or temporary images.

The full runner suite now has 74 passing tests with one Windows
symlink-privilege skip.

## GPT-5.4 four-task credential-free preflight

Run the OpenAI Responses adapter through every representative pilot task
without a credential or network request:

```powershell
python -m benchmark.runner.credential_free_dry_run `
  --matrix gpt54 `
  --output-root artifacts/gpt54-pilot-preflight-20260811
```

The preflight uses scripted OpenAI Responses payloads and exercises the shared
runner, logical tools, task probes, hidden evaluator, finalizer, and evidence
validator. It remains a validation-phase check: it does not create a pilot
observation or bypass the frozen-manifest execution gate.
