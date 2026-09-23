from __future__ import annotations

import json
import hashlib
import re
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from ..contracts import (
    SUBMIT_MARKER,
    TRANSPORT_CONTRACT_VERSION,
    ModelTurn,
    ToolCall,
    TransportAttempt,
    TransportContractError,
    TransportInfrastructureError,
    TransportRequest,
    UsageDelta,
)
from ..transport_contract import (
    ErrorDisposition,
    ProviderError,
    decide_retry,
    normalize_tool_arguments,
    validate_model_turn,
    validate_transport_request,
)


QWEN_2_5_CODER_7B_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
QWEN_FENCED_TOOL_NORMALIZER_ID = "qwen-fenced-tool-json-v3"
_JSON_FENCE = re.compile(r"```json\r?\n(?P<body>\{[^\r\n]*\})\r?\n```")


@dataclass(frozen=True)
class QwenWireResponse:
    """JSON response plus HTTP metadata exposed by the live HTTPS bridge."""

    payload: Mapping[str, Any]
    http_status: int = 200
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not 100 <= self.http_status <= 599:
            raise ValueError("http_status is outside the valid HTTP range")


@dataclass(frozen=True)
class QwenModelTurn(ModelTurn):
    """Common model turn plus Qwen-only response-normalization audit."""

    normalization_metadata: dict[str, Any] | None = None


class QwenProviderRequestError(RuntimeError):
    """Sanitized failure raised by the live Hugging Face/vLLM HTTPS bridge."""

    def __init__(
        self,
        detail: str,
        *,
        http_status: int | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        retry_after_seconds: float | None = None,
        provider_request_id: str | None = None,
        is_timeout: bool = False,
        is_connection_error: bool = False,
    ) -> None:
        super().__init__(detail)
        self.provider_error = ProviderError(
            http_status=http_status,
            error_code=error_code,
            error_type=error_type,
            retry_after_seconds=retry_after_seconds,
            is_timeout=is_timeout,
            is_connection_error=is_connection_error,
        )
        self.provider_request_id = provider_request_id


QwenRequester = Callable[[dict[str, Any], float], QwenWireResponse | Mapping[str, Any]]


class QwenVllmTransport:
    """Qwen2.5-Coder vLLM Chat Completions adapter with an injected requester."""

    provider_name = "qwen2_5_coder_7b_instruct"
    contract_version = TRANSPORT_CONTRACT_VERSION

    def __init__(
        self,
        requester: QwenRequester,
        *,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not callable(requester):
            raise TypeError("requester must be callable")
        self._requester = requester
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep

    def generate(self, request: TransportRequest) -> ModelTurn:
        validate_transport_request(request)
        payload = serialize_qwen_chat_request(request)
        attempts: list[TransportAttempt] = []

        for attempt_number in range(1, request.policy.retry.max_attempts + 1):
            started = self._monotonic()
            try:
                contextual_request = getattr(
                    self._requester, "request_with_meter_context", None
                )
                if getattr(self._requester, "requires_paid_meter_context", False):
                    if not callable(contextual_request):
                        raise TransportContractError(
                            "Metered requester omitted contextual request method"
                        )
                    wire = contextual_request(
                        _json_clone(payload),
                        request.policy.request_timeout_seconds,
                        logical_request_id=request.logical_request_id,
                        attempt_number=attempt_number,
                        transport_policy=request.policy,
                    )
                else:
                    wire = self._requester(
                        _json_clone(payload), request.policy.request_timeout_seconds
                    )
                response = _coerce_wire_response(wire)
                raw_payload = _json_object(response.payload, "Qwen response payload")
                provider_request_id = _provider_request_id(response, raw_payload)
                if not 200 <= response.http_status <= 299:
                    raise _http_error(response, raw_payload, provider_request_id)
                elapsed = max(0.0, self._monotonic() - started)
                attempts.append(
                    TransportAttempt(
                        attempt_number,
                        "success",
                        elapsed,
                        provider_request_id=provider_request_id,
                    )
                )
                turn = _normalize_response(
                    raw_payload, tool_definitions=request.tool_definitions
                )
                turn = replace(turn, transport_attempts=tuple(attempts))
                validate_model_turn(turn)
                return turn
            except Exception as error:
                provider_error = _request_error(error)
                if provider_error is None:
                    raise
                elapsed = max(0.0, self._monotonic() - started)
                decision = decide_retry(
                    provider_error.provider_error,
                    attempt_number=attempt_number,
                    policy=request.policy,
                )
                if decision.disposition is ErrorDisposition.RETRY:
                    attempts.append(
                        TransportAttempt(
                            attempt_number,
                            "retryable_error",
                            elapsed,
                            error_kind=decision.kind.value,
                            http_status=provider_error.provider_error.http_status,
                            provider_error_code=provider_error.provider_error.error_code,
                            provider_request_id=provider_error.provider_request_id,
                            retry_delay_seconds=decision.retry_delay_seconds,
                        )
                    )
                    self._sleep(decision.retry_delay_seconds or 0.0)
                    continue
                attempts.append(
                    TransportAttempt(
                        attempt_number,
                        "terminal_error",
                        elapsed,
                        error_kind=decision.kind.value,
                        http_status=provider_error.provider_error.http_status,
                        provider_error_code=provider_error.provider_error.error_code,
                        provider_request_id=provider_error.provider_request_id,
                    )
                )
                raise TransportInfrastructureError(
                    f"Qwen/vLLM transport failed: {decision.kind.value} "
                    f"({decision.reason})",
                    attempts=len(attempts),
                    attempt_records=tuple(attempts),
                ) from error

        raise TransportContractError("Qwen/vLLM retry loop exited without a result")


def serialize_qwen_chat_request(request: TransportRequest) -> dict[str, Any]:
    """Convert a provider-neutral request to vLLM's Chat Completions shape."""

    validate_transport_request(request)
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role in {"system", "user"}:
            messages.append({"role": message.role, "content": message.content})
            continue
        if message.role == "assistant":
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": message.content if message.content else None,
            }
            if message.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(assistant)
            continue
        messages.append(
            {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        )

    tools = [
        {
            "type": "function",
            "function": {
                "name": definition["name"],
                "description": definition["description"],
                "parameters": _json_clone(definition["input_schema"]),
                "strict": True,
            },
        }
        for definition in request.tool_definitions
    ]
    return {
        "model": QWEN_2_5_CODER_7B_MODEL,
        "messages": messages,
        "tools": tools,
        "max_tokens": request.policy.max_output_tokens,
        "temperature": request.policy.temperature,
        "tool_choice": request.policy.tool_choice,
        "parallel_tool_calls": request.policy.parallel_tool_calls,
        "stream": request.policy.stream,
    }


def _normalize_response(
    payload: dict[str, Any], *, tool_definitions: tuple[dict[str, Any], ...]
) -> QwenModelTurn:
    response_id = _optional_nonempty_string(payload.get("id"), "response id")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise TransportContractError("Qwen response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise TransportContractError("Qwen response choice must be an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise TransportContractError("Qwen response message must be an object")

    content = message.get("content")
    if content is None:
        text = ""
    elif isinstance(content, str):
        text = content
    else:
        raise TransportContractError("Qwen assistant content must be text or null")

    refusal = message.get("refusal")
    saw_refusal = False
    if refusal is not None:
        if not isinstance(refusal, str):
            raise TransportContractError("Qwen refusal must be text or null")
        if refusal:
            saw_refusal = True
            text += refusal

    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        raise TransportContractError("Qwen tool_calls must be a list or null")
    tool_calls: list[ToolCall] = []
    for call_index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            raise TransportContractError(
                f"Qwen tool call {call_index} must be an object"
            )
        if raw_call.get("type") != "function":
            raise TransportContractError("Qwen returned a non-function tool call")
        call_id = _required_nonempty_string(raw_call.get("id"), "tool call id")
        function = raw_call.get("function")
        if not isinstance(function, dict):
            raise TransportContractError("Qwen tool call function must be an object")
        name = _required_nonempty_string(function.get("name"), "function name")
        arguments, argument_error = normalize_tool_arguments(function.get("arguments"))
        tool_calls.append(
            ToolCall(call_id, name, arguments, argument_error=argument_error)
        )

    normalization_metadata: dict[str, Any] = {
        "compatibility_normalizer": {
            "id": QWEN_FENCED_TOOL_NORMALIZER_ID,
            "applied": False,
            "reason": "native_tool_calls_present" if tool_calls else "not_eligible",
        }
    }
    if not tool_calls:
        compatibility_call, compatibility_audit, normalized_text = _normalize_fenced_tool_call(
            content=text,
            response_id=response_id,
            raw_finish_reason=choice.get("finish_reason"),
            saw_refusal=saw_refusal,
            tool_definitions=tool_definitions,
        )
        normalization_metadata = {
            "compatibility_normalizer": compatibility_audit
        }
        if compatibility_call is not None:
            tool_calls.append(compatibility_call)
            text = normalized_text

    finish_reason = _finish_reason(
        choice.get("finish_reason"),
        has_tool_calls=bool(tool_calls),
        saw_refusal=saw_refusal,
    )
    return QwenModelTurn(
        text=text,
        tool_calls=tuple(tool_calls),
        raw_payload=_json_clone(payload),
        response_id=response_id,
        usage=_normalize_usage(payload.get("usage")),
        finish_reason=finish_reason,
        normalization_metadata=normalization_metadata,
    )


def _normalize_fenced_tool_call(
    *,
    content: str,
    response_id: str | None,
    raw_finish_reason: Any,
    saw_refusal: bool,
    tool_definitions: tuple[dict[str, Any], ...],
) -> tuple[ToolCall | None, dict[str, Any], str]:
    audit: dict[str, Any] = {
        "id": QWEN_FENCED_TOOL_NORMALIZER_ID,
        "applied": False,
    }
    if saw_refusal:
        audit["reason"] = "refusal_present"
        return None, audit, content
    if raw_finish_reason != "stop":
        audit["reason"] = "finish_reason_not_stop"
        return None, audit, content
    if response_id is None:
        audit["reason"] = "response_id_missing"
        return None, audit, content
    matches = list(_JSON_FENCE.finditer(content))
    representation = "fenced"
    if len(matches) > 1:
        audit["reason"] = "eligible_json_fence_count_not_one"
        return None, audit, content
    if len(matches) == 1:
        match = matches[0]
        prefix = content[: match.start()]
        suffix = content[match.end() :]
        body = match.group("body")
    else:
        if "```" in content:
            audit["reason"] = "fence_present_without_eligible_json_fence"
            return None, audit, content
        spans, span_issue = _top_level_object_spans(content)
        if span_issue is not None:
            audit["reason"] = span_issue
            return None, audit, content
        if len(spans) != 1:
            audit["reason"] = "eligible_unfenced_json_object_count_not_one"
            return None, audit, content
        start, end = spans[0]
        prefix = content[:start]
        suffix = content[end:]
        body = content[start:end]
        if "\r" in body or "\n" in body:
            audit["reason"] = "unfenced_body_not_single_line"
            return None, audit, content
        representation = "unfenced"
    residual = prefix + suffix
    if "```" in residual:
        audit["reason"] = "additional_fence_present"
        return None, audit, content
    if SUBMIT_MARKER in residual:
        audit["reason"] = "submit_marker_present"
        return None, audit, content
    if "{" in residual or "}" in residual:
        audit["reason"] = "additional_object_like_content_present"
        return None, audit, content
    try:
        candidate = json.loads(body, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        audit["reason"] = f"{representation}_body_invalid_json"
        return None, audit, content
    if not isinstance(candidate, dict) or set(candidate) != {"name", "arguments"}:
        audit["reason"] = "tool_object_keys_mismatch"
        return None, audit, content
    name = candidate.get("name")
    arguments = candidate.get("arguments")
    if not isinstance(name, str) or not name:
        audit["reason"] = "tool_name_invalid"
        return None, audit, content
    definitions = {
        definition.get("name"): definition
        for definition in tool_definitions
        if isinstance(definition, dict)
    }
    definition = definitions.get(name)
    if definition is None:
        audit["reason"] = "tool_name_not_frozen"
        return None, audit, content
    schema = definition.get("input_schema")
    if not isinstance(arguments, dict) or not isinstance(schema, dict):
        audit["reason"] = "arguments_not_object"
        return None, audit, content
    schema_issue = _strict_object_schema_issue(arguments, schema)
    if schema_issue is not None:
        audit["reason"] = f"arguments_schema_mismatch:{schema_issue}"
        return None, audit, content
    canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
    call_id = "compat_" + hashlib.sha256(
        f"{response_id}\n{canonical}".encode("utf-8")
    ).hexdigest()[:32]
    audit.update(
        {
            "applied": True,
            "reason": f"single_{representation}_tool_json_with_preserved_prose",
            "source_representation": representation,
            "source_content_sha256": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            "tool_name": name,
            "prefix_sha256": hashlib.sha256(prefix.encode("utf-8")).hexdigest(),
            "suffix_sha256": hashlib.sha256(suffix.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                residual.encode("utf-8")
            ).hexdigest(),
            "synthetic_call_id": True,
            "semantic_repair_performed": False,
        }
    )
    return ToolCall(call_id, name, arguments), audit, residual


def _top_level_object_spans(content: str) -> tuple[list[tuple[int, int]], str | None]:
    """Locate complete outer brace spans without interpreting prose as JSON."""

    spans: list[tuple[int, int]] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(content):
        if depth == 0:
            if character == "{":
                start = index
                depth = 1
            elif character == "}":
                return [], "unmatched_unfenced_object_brace"
            continue
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                if start is None:
                    return [], "unmatched_unfenced_object_brace"
                spans.append((start, index + 1))
                start = None
    if depth != 0 or in_string:
        return [], "unmatched_unfenced_object_brace"
    return spans, None


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_object_schema_issue(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        return "unsupported_schema"
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        return "unsupported_schema"
    if set(arguments) != set(required) or set(required) != set(properties):
        return "property_set"
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict) or property_schema.get("type") != "string":
            return "unsupported_property_schema"
        if not isinstance(value, str):
            return f"{name}_type"
        minimum = property_schema.get("minLength")
        maximum = property_schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            return f"{name}_minLength"
        if isinstance(maximum, int) and len(value) > maximum:
            return f"{name}_maxLength"
    return None


def _normalize_usage(value: Any) -> UsageDelta | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TransportContractError("Qwen usage must be an object or null")
    prompt_tokens = _required_nonnegative_int(value.get("prompt_tokens"), "prompt_tokens")
    completion_tokens = _required_nonnegative_int(
        value.get("completion_tokens"), "completion_tokens"
    )
    total_tokens = _optional_nonnegative_int(value.get("total_tokens"), "total_tokens")
    prompt_details = value.get("prompt_tokens_details") or {}
    completion_details = value.get("completion_tokens_details") or {}
    if not isinstance(prompt_details, dict) or not isinstance(completion_details, dict):
        raise TransportContractError("Qwen token detail fields must be objects")
    cached_tokens = _optional_nonnegative_int(
        prompt_details.get("cached_tokens"), "cached_tokens"
    )
    reasoning_tokens = _optional_nonnegative_int(
        completion_details.get("reasoning_tokens"), "reasoning_tokens"
    )
    try:
        return UsageDelta(
            prompt_tokens,
            completion_tokens,
            cached_input_tokens=cached_tokens,
            reasoning_output_tokens=reasoning_tokens,
            provider_reported_total_tokens=total_tokens,
        )
    except ValueError as error:
        raise TransportContractError(f"Invalid Qwen usage: {error}") from error


def _finish_reason(value: Any, *, has_tool_calls: bool, saw_refusal: bool) -> str:
    if value == "length":
        return "max_output_tokens"
    if value == "content_filter":
        return "content_filter"
    if saw_refusal:
        return "refusal"
    if value in {"tool_calls", "function_call"} or has_tool_calls:
        return "tool_calls"
    if value == "stop":
        return "completed"
    if not isinstance(value, str) and value is not None:
        raise TransportContractError("Qwen finish_reason must be text or null")
    return "other"


def _request_error(error: Exception) -> QwenProviderRequestError | None:
    if isinstance(error, QwenProviderRequestError):
        return error
    if isinstance(error, TimeoutError):
        return QwenProviderRequestError("Qwen request timed out", is_timeout=True)
    if isinstance(error, ConnectionError):
        return QwenProviderRequestError(
            "Qwen connection failed", is_connection_error=True
        )
    return None


def _coerce_wire_response(
    value: QwenWireResponse | Mapping[str, Any],
) -> QwenWireResponse:
    if isinstance(value, QwenWireResponse):
        return value
    if isinstance(value, Mapping):
        return QwenWireResponse(value)
    raise TransportContractError(
        "Qwen requester must return an object payload or QwenWireResponse"
    )


def _http_error(
    response: QwenWireResponse,
    payload: dict[str, Any],
    provider_request_id: str | None,
) -> QwenProviderRequestError:
    error = payload.get("error")
    error_object = error if isinstance(error, dict) else {}
    headers = _lower_headers(response.headers)
    return QwenProviderRequestError(
        "Qwen/vLLM returned a non-success HTTP response",
        http_status=response.http_status,
        error_code=_optional_string(error_object.get("code")),
        error_type=_optional_string(error_object.get("type")),
        retry_after_seconds=_retry_after_seconds(headers.get("retry-after")),
        provider_request_id=provider_request_id,
    )


def _provider_request_id(
    response: QwenWireResponse, payload: dict[str, Any]
) -> str | None:
    headers = _lower_headers(response.headers)
    return _optional_string(headers.get("x-request-id")) or _optional_string(
        payload.get("id")
    )


def _lower_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).casefold(): str(value) for key, value in headers.items()}


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _json_clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as error:
        raise TransportContractError("Qwen wire value is not JSON serializable") from error


def _json_object(value: Any, label: str) -> dict[str, Any]:
    cloned = _json_clone(value)
    if not isinstance(cloned, dict):
        raise TransportContractError(f"{label} must be an object")
    return cloned


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TransportContractError(f"Qwen {label} must be a string")
    return value


def _required_nonempty_string(value: Any, label: str) -> str:
    text = _required_string(value, label)
    if not text:
        raise TransportContractError(f"Qwen {label} must be non-empty")
    return text


def _optional_nonempty_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _required_nonempty_string(value, label)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransportContractError(f"Qwen {label} must be a non-negative integer")
    return value


def _optional_nonnegative_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _required_nonnegative_int(value, label)
