# Provider Transport Contract

Status: frozen common contract with one reviewed Qwen transport-compatibility
candidate; Qwen compatibility live validation pending  
Contract version: 1.0.0  
Date: 2026-08-09

The machine-readable freeze is
`benchmark/config/transport_contract.v1.json`; conformance tests verify that its
shared policy is identical to the code defaults.

- Shared `TransportPolicy` SHA-256:
  `ed24acaef1d304612680c6bfc9a635d0fad836b19beb076f16a60f89cfbc81d4`
- Machine-readable freeze SHA-256:
  `c1bee59037a1011d18add6cecf408f1d5bd068649313e657c30873aa9d05bafb`

## Boundary

The transport boundary converts one provider-neutral `TransportRequest` into
one provider-neutral `ModelTurn`. The shared runner owns context selection,
logical action counting, tool execution, submission detection, and run-level
stopping. A provider adapter owns only request serialization, one provider API
exchange including bounded retries, raw-response retention, and normalization.

The two API systems must receive the same retained messages, task brief, four
logical tool schemas, and shared generation/retry policy. Provider-specific
wire formats may differ, but they cannot add tools, hidden instructions, hosted
execution, provider-side retrieval, or provider-specific context content.

## Frozen normalized request

Every call receives:

- `logical_request_id`: `<run_id>:turn:<n>`;
- `model_turn`: one-based model turn number;
- the complete retained tuple of `ContextMessage` values;
- the exact four `TOOL_DEFINITIONS` values;
- `TransportPolicy` version `1.0.0`.

The frozen default policy is:

| Field | Value |
|---|---:|
| Request timeout | 120 seconds per attempt |
| Maximum attempts | 3 total (initial plus two retries) |
| Deterministic retry delays | 1 second, then 2 seconds |
| Maximum accepted `Retry-After` | 30 seconds |
| Maximum output | 4096 tokens |
| Temperature | 0.0 |
| Tool choice | `auto` |
| Parallel tool calls | allowed |
| Streaming | disabled |

Multiple calls returned in one response are retained in provider order. The
shared run loop executes them sequentially in that order, and each call that
reaches the logical executor consumes one action. Provider retries never
consume logical actions, but their time remains part of the run wall clock.

The runner writes a SHA-256 fingerprint of every normalized request and the
shared policy to `adapter_decisions.jsonl`. All attempts for one logical request
must use semantically identical messages, tools, and generation settings.

## Provider serialization profiles

### OpenAI GPT-5.4

- Endpoint family: Responses API `/v1/responses`.
- Frozen model: `gpt-5.4-2026-03-05`.
- `store=false`; no `previous_response_id`; retained history is supplied by the
  shared runner on every turn.
- `reasoning.effort=none`, matching the non-reasoning Qwen instruct baseline and
  avoiding provider-only persisted reasoning state.
- Function tools use `strict=true`; their `parameters` are the unchanged common
  `input_schema` values.
- Only function tools are sent. OpenAI hosted shell, apply-patch, web, file,
  computer-use, code-interpreter, MCP, and tool-search capabilities are not
  exposed.
- The adapter must disable SDK-level retries so the shared retry policy is the
  only retry mechanism.

The credential-free adapter is implemented in
`benchmark/runner/api_wrapper/transports/openai_responses.py`. It accepts an
injected requester, so conformance tests can inspect the exact Responses API
payload and return raw JSON without importing an SDK or reading an API key. It
serializes retained assistant calls as `function_call` items and tool results
as `function_call_output` items, normalizes ordered text/calls and detailed
usage into `ModelTurn`, preserves the complete raw payload, and owns the frozen
retry/attempt audit. The live bridge performs only authenticated HTTPS I/O and
translates failures into the adapter's sanitized request error; it does not add
implicit retries or change payload semantics. Its standard-library
implementation is in
`benchmark/runner/api_wrapper/transports/live_http.py` and is offline-tested
through an injected URL opener.

OpenAI documents that GPT-5.4 supports the Responses API and function calling,
and identifies `gpt-5.4-2026-03-05` as its dated snapshot. Its function-calling
guide recommends strict schemas, requires all properties to be required with
`additionalProperties=false`, and links tool outputs to calls using `call_id`.

### Qwen2.5-Coder-7B-Instruct

- Endpoint family: managed Hugging Face Inference Endpoint using vLLM's
  OpenAI-compatible `/v1/chat/completions` interface.
- Model family: `Qwen/Qwen2.5-Coder-7B-Instruct`; the exact repository commit,
  endpoint region/hardware, and vLLM version remain experiment-configuration
  freeze fields and must be non-null before pilot execution.
- Messages use the OpenAI-compatible Chat Completions roles and tool-call/tool
  result linkage.
- Tool definitions are the unchanged common schemas wrapped in the endpoint's
  function-tool envelope. Provider extensions must not alter their semantics.
- The endpoint must be launched with a Qwen-compatible tool-call parser and
  automatic tool choice enabled. Those exact launch values will be recorded in
  the system configuration manifest.
- Client/SDK implicit retries must be disabled.

The credential-free adapter is implemented in
`benchmark/runner/api_wrapper/transports/qwen_vllm.py`. It accepts an injected
requester and serializes the retained common context into vLLM's
OpenAI-compatible Chat Completions messages, including assistant `tool_calls`
and linked `tool` results. Strict function definitions wrap the unchanged
common schemas. Ordered text/calls, provider-native usage, finish reasons, raw
payloads, and the frozen retry audit normalize into the same `ModelTurn` used
by GPT-5.4.

After `retry-006`, `retry-007`, and `retry-008` all returned the same single
Markdown-fenced function JSON under `tool_choice=auto`, the Qwen adapter gained
one narrowly bounded compatibility candidate,
`qwen-fenced-tool-json-v1`. It is a response-format adapter, not a semantic
repair. It applies only when native `tool_calls` are empty, the raw finish
reason is exactly `stop`, a provider response ID is present, and the complete
assistant content is exactly one lowercase `json` fence containing a
single-line object whose only keys are `name` and `arguments`. The tool name
must be one of the four frozen common tools and the arguments must exactly
satisfy that tool's frozen strict schema. No surrounding text, extra key,
unknown tool, missing/extra argument, wrong type, invalid JSON, multiple call,
refusal, or non-`stop` response is converted.

An eligible response becomes exactly one common `ToolCall`. Its call ID is
deterministically synthesized from the provider response ID and canonical tool
JSON solely to support call/result linkage. The raw provider payload is retained
unchanged, normalized text becomes empty, and the evidence records whether the
normalizer applied, its reason, the source-content SHA-256, the synthetic-ID
flag, and `semantic_repair_performed=false`. Native provider tool calls always
bypass this compatibility path. The machine-readable boundary is
`benchmark/config/qwen_fenced_tool_normalizer.candidate.json`; it cannot be
promoted until the three-request live smoke proves exact text, converted call,
and linked tool-result behavior.

Current vLLM documentation identifies the `hermes` parser for Qwen2.5 and
requires automatic tool choice to be enabled for `tool_choice=auto`. The
credential-free candidate in `benchmark/config/qwen_deployment.candidate.json`
now selects Hub commit `c03e6d358207e414f1eca0bb1891e29f1db0e242`, AWS
`us-east-1`, one NVIDIA L4 24 GB, vLLM 0.26.0 pinned by its Linux/amd64
container digest, a 32768-token cap, single-sequence execution, automatic tool
choice, and the `hermes` parser. These are deployment requirements, not
request-payload fields. They remain candidate values until the funded live
Endpoint passes all six promotion gates. The later live bridge may add
authentication and the Endpoint URL only outside the payload; it may not alter
common messages, tools, generation settings, or retries.

Hugging Face documents dedicated vLLM endpoints and an OpenAI-compatible chat
completion/tool-calling interface. Adapter conformance tests, rather than the
compatibility label alone, determine whether the frozen endpoint is usable.
The matching requester in `live_http.py` restricts credential-bearing requests
to HTTPS port 443 hosts under `.endpoints.huggingface.cloud`, appends the frozen
chat-completions route, bounds response decoding, and adds no payload fields or
implicit retries. Paid live compatibility remains a promotion gate.

## Normalized response

A successful adapter call returns exactly one `ModelTurn`:

- `text`: observable assistant text, concatenated in provider output order;
- `tool_calls`: ordered `ToolCall` values with provider `call_id`, common tool
  name, and object arguments;
- `raw_payload`: the complete JSON-serializable provider response;
- `response_id`: provider response/request identifier where available;
- `usage`: one `UsageDelta` when the provider reports usage;
- `finish_reason`: one of `completed`, `tool_calls`, `max_output_tokens`,
  `content_filter`, `refusal`, or `other`;
- `transport_attempts`: a contiguous, sanitized attempt audit ending in
  `success`.
- `normalization_metadata`: JSON-serializable adapter audit, including the
  Qwen compatibility decision when applicable.

The adapter must never synthesize a successful tool call by repairing malformed
JSON or changing tool semantics. The only synthetic call is the exact,
schema-valid Qwen fenced-JSON compatibility case above; it copies the selected
tool name and arguments without correction. Native invalid or non-object
argument JSON is normalized to empty arguments plus a stable `argument_error`
code. The logical call still consumes one action and returns an observable tool
error to the model. This treats malformed tool use as model behaviour, not
provider infrastructure failure.

An accepted provider response must contain observable text or at least one tool
call. Duplicate/empty call IDs, an unknown normalized finish reason,
non-serializable raw data, broken call/result linkage, or an invalid attempt
sequence violates the adapter contract and becomes `runner_error`.

## Usage

`UsageDelta` preserves:

- provider-reported input and output tokens;
- cached input tokens when available;
- reasoning output tokens when available;
- provider-reported total tokens;
- monetary cost and currency only when the provider directly supplies or a
  separately frozen pricing rule can reproduce them.

Input/output totals are accumulated only for successful provider responses.
Failed retry attempts do not invent zero-token usage. If any successful turn
lacks required token usage, run-level token usage remains `unavailable`; raw
provider usage and attempt evidence are still retained. Cross-provider token
counts remain provider-native measurements and are not treated as identical
tokenizations.

## Retry and error mapping

| Condition | Retry? | Final wrapper classification |
|---|---|---|
| Connection failure or request timeout | Yes, within 3 attempts | `infrastructure_failure` if exhausted |
| HTTP 408, 409, or 425 | Yes | `infrastructure_failure` if exhausted |
| HTTP 429 rate limit | Yes; honor bounded `Retry-After` | `infrastructure_failure` if exhausted |
| HTTP 500, 502, 503, or 504 | Yes | `infrastructure_failure` if exhausted |
| `Retry-After` greater than 30 seconds | No | `infrastructure_failure` |
| Authentication/permission failure | No | `infrastructure_failure` |
| Credit, quota, billing, spend, or usage limit | No | `infrastructure_failure` |
| Invalid request, unsupported model, or endpoint configuration | No | `infrastructure_failure` |
| Provider refusal/content filter with observable response | No | Normal `ModelTurn`; model behaviour |
| Malformed provider tool arguments | No | Observable counted tool error |
| Adapter violates normalized types/invariants | No | `runner_error` |
| Logical tool infrastructure fails | Not a transport retry | `infrastructure_failure` |

`Retry-After` is used only when it is at most 30 seconds; the actual delay is
the greater of the header and the frozen 1/2-second delay. There is no random
jitter, keeping retry behaviour auditable. The final failure records every
attempt's number, outcome, elapsed time, normalized error kind, HTTP status,
provider error code, provider request ID, and retry delay without recording
credentials.

## Fields intentionally not frozen by this contract

The transport *structure and behaviour* above are frozen. These experiment
configuration values still require the scheduled pilot/freeze decision:

- final common system prompt and context-pruning limit;
- promotion evidence for the selected Qwen repository commit, vLLM image,
  endpoint region/hardware, memory bound, and tool parser;
- endpoint URLs and credential identifiers (never secret values);
- SDK versions and configuration hashes;
- pricing basis used for derived cost.

Changing a value in this section does not change contract version 1.0.0, but it
must be recorded in the experiment configuration manifest before pilot/main
runs. Changing request/response fields, retry/error semantics, or normalized
tool behaviour requires a transport contract version change.

## Cross-provider symmetry conformance

`benchmark/runner/tests/test_transport_symmetry.py` verifies the common
contract above the two wire formats. Equivalent retained histories are reduced
to one semantic sequence of system/user/assistant text, ordered function calls,
and call-linked outputs; both adapters expose the same four schemas and shared
generation policy. Equivalent mock responses must produce identical observable
text, ordered `ToolCall` values (including malformed-argument codes), detailed
`UsageDelta`, and normalized finish reasons.

The suite also runs the retry matrix through both adapters: HTTP 408, 409, 425,
429, 500, 502, 503, and 504 produce matching retry audits, while
authentication, permission, unavailable-model, invalid-request, quota, and
over-limit `Retry-After` cases produce matching terminal classifications.
Provider-specific response IDs and raw payload formats intentionally remain
different and are not asserted as equal.

## Official interface references

- [OpenAI GPT-5.4 model](https://developers.openai.com/api/docs/models/gpt-5.4)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes)
- [Hugging Face dedicated vLLM endpoints](https://huggingface.co/docs/inference-endpoints/engines/vllm)
- [Hugging Face OpenAI-compatible inference and tool calling](https://huggingface.co/docs/huggingface_hub/en/guides/inference)
