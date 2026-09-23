from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from ..contracts import (
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


OPENAI_GPT_5_4_MODEL = "gpt-5.4-2026-03-05"


@dataclass(frozen=True)
class OpenAIWireResponse:
    """JSON response plus the small amount of HTTP metadata used by the adapter."""

    payload: Mapping[str, Any]
    http_status: int = 200
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not 100 <= self.http_status <= 599:
            raise ValueError("http_status is outside the valid HTTP range")


class OpenAIProviderRequestError(RuntimeError):
    """Sanitized failure raised by the live OpenAI HTTPS bridge."""

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


OpenAIRequester = Callable[
    [dict[str, Any], float], OpenAIWireResponse | Mapping[str, Any]
]


class OpenAIResponsesTransport:
    """GPT-5.4 Responses API adapter with an injected, credential-free requester."""

    provider_name = "openai_gpt_5_4"
    contract_version = TRANSPORT_CONTRACT_VERSION

    def __init__(
        self,
        requester: OpenAIRequester,
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
        payload = serialize_openai_responses_request(request)
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
                raw_payload = _json_object(response.payload, "OpenAI response payload")
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
                turn = _normalize_response(raw_payload)
                turn = replace(turn, transport_attempts=tuple(attempts))
                validate_model_turn(turn)
                return turn
            except OpenAIProviderRequestError as error:
                elapsed = max(0.0, self._monotonic() - started)
                decision = decide_retry(
                    error.provider_error,
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
                            http_status=error.provider_error.http_status,
                            provider_error_code=error.provider_error.error_code,
                            provider_request_id=error.provider_request_id,
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
                        http_status=error.provider_error.http_status,
                        provider_error_code=error.provider_error.error_code,
                        provider_request_id=error.provider_request_id,
                    )
                )
                raise TransportInfrastructureError(
                    f"OpenAI Responses transport failed: {decision.kind.value} "
                    f"({decision.reason})",
                    attempts=len(attempts),
                    attempt_records=tuple(attempts),
                ) from error
            except TimeoutError as error:
                provider_error = OpenAIProviderRequestError(
                    "OpenAI request timed out", is_timeout=True
                )
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
                    )
                )
                raise TransportInfrastructureError(
                    "OpenAI Responses transport failed: timeout (attempts_exhausted)",
                    attempts=len(attempts),
                    attempt_records=tuple(attempts),
                ) from error
            except ConnectionError as error:
                provider_error = OpenAIProviderRequestError(
                    "OpenAI connection failed", is_connection_error=True
                )
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
                    )
                )
                raise TransportInfrastructureError(
                    "OpenAI Responses transport failed: connection_error "
                    "(attempts_exhausted)",
                    attempts=len(attempts),
                    attempt_records=tuple(attempts),
                ) from error

        raise TransportContractError("OpenAI retry loop exited without a result")


def serialize_openai_responses_request(request: TransportRequest) -> dict[str, Any]:
    """Convert a provider-neutral request into the frozen Responses API shape."""

    validate_transport_request(request)
    input_items: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role in {"system", "user"}:
            input_items.append({"role": message.role, "content": message.content})
            continue
        if message.role == "assistant":
            if message.content:
                input_items.append(
                    {"role": "assistant", "content": message.content}
                )
            for call in message.tool_calls:
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
            continue
        input_items.append(
            {
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": message.content,
            }
        )

    tools = [
        {
            "type": "function",
            "name": definition["name"],
            "description": definition["description"],
            "parameters": _json_clone(definition["input_schema"]),
            "strict": True,
        }
        for definition in request.tool_definitions
    ]
    return {
        "model": OPENAI_GPT_5_4_MODEL,
        "input": input_items,
        "tools": tools,
        "store": False,
        "reasoning": {"effort": "none"},
        "max_output_tokens": request.policy.max_output_tokens,
        "temperature": request.policy.temperature,
        "tool_choice": request.policy.tool_choice,
        "parallel_tool_calls": request.policy.parallel_tool_calls,
        "stream": request.policy.stream,
    }


def _normalize_response(payload: dict[str, Any]) -> ModelTurn:
    response_id = _optional_nonempty_string(payload.get("id"), "response id")
    output = payload.get("output")
    if not isinstance(output, list):
        raise TransportContractError("OpenAI response output must be a list")

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    saw_refusal = False
    for item_index, item in enumerate(output):
        if not isinstance(item, dict):
            raise TransportContractError(
                f"OpenAI output item {item_index} must be an object"
            )
        item_type = item.get("type")
        if item_type == "reasoning":
            continue
        if item_type == "function_call":
            call_id = _required_nonempty_string(item.get("call_id"), "function call_id")
            name = _required_nonempty_string(item.get("name"), "function name")
            arguments, argument_error = normalize_tool_arguments(item.get("arguments"))
            tool_calls.append(
                ToolCall(call_id, name, arguments, argument_error=argument_error)
            )
            continue
        if item_type != "message":
            raise TransportContractError(
                f"Unsupported OpenAI output item type: {item_type!r}"
            )
        content = item.get("content")
        if not isinstance(content, list):
            raise TransportContractError("OpenAI message content must be a list")
        for content_index, part in enumerate(content):
            if not isinstance(part, dict):
                raise TransportContractError(
                    f"OpenAI content item {content_index} must be an object"
                )
            content_type = part.get("type")
            if content_type == "output_text":
                text_parts.append(
                    _required_string(part.get("text"), "output_text text")
                )
            elif content_type == "refusal":
                saw_refusal = True
                text_parts.append(
                    _required_string(part.get("refusal"), "refusal text")
                )
            else:
                raise TransportContractError(
                    f"Unsupported OpenAI message content type: {content_type!r}"
                )

    finish_reason = _finish_reason(
        payload, has_tool_calls=bool(tool_calls), saw_refusal=saw_refusal
    )
    usage = _normalize_usage(payload.get("usage"))
    return ModelTurn(
        text="".join(text_parts),
        tool_calls=tuple(tool_calls),
        raw_payload=_json_clone(payload),
        response_id=response_id,
        usage=usage,
        finish_reason=finish_reason,
    )


def _normalize_usage(value: Any) -> UsageDelta | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TransportContractError("OpenAI usage must be an object or null")
    input_tokens = _required_nonnegative_int(value.get("input_tokens"), "input_tokens")
    output_tokens = _required_nonnegative_int(
        value.get("output_tokens"), "output_tokens"
    )
    total_tokens = _optional_nonnegative_int(value.get("total_tokens"), "total_tokens")
    input_details = value.get("input_tokens_details") or {}
    output_details = value.get("output_tokens_details") or {}
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise TransportContractError("OpenAI token detail fields must be objects")
    cached_tokens = _optional_nonnegative_int(
        input_details.get("cached_tokens"), "cached_tokens"
    )
    reasoning_tokens = _optional_nonnegative_int(
        output_details.get("reasoning_tokens"), "reasoning_tokens"
    )
    try:
        return UsageDelta(
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_tokens,
            reasoning_output_tokens=reasoning_tokens,
            provider_reported_total_tokens=total_tokens,
        )
    except ValueError as error:
        raise TransportContractError(f"Invalid OpenAI usage: {error}") from error


def _finish_reason(
    payload: dict[str, Any], *, has_tool_calls: bool, saw_refusal: bool
) -> str:
    status = payload.get("status")
    if not isinstance(status, str):
        raise TransportContractError("OpenAI response status must be a string")
    if status == "incomplete":
        details = payload.get("incomplete_details")
        if not isinstance(details, dict):
            return "other"
        reason = details.get("reason")
        if reason == "max_output_tokens":
            return "max_output_tokens"
        if reason == "content_filter":
            return "content_filter"
        return "other"
    if saw_refusal:
        return "refusal"
    if has_tool_calls:
        return "tool_calls"
    if status == "completed":
        return "completed"
    return "other"


def _coerce_wire_response(
    value: OpenAIWireResponse | Mapping[str, Any],
) -> OpenAIWireResponse:
    if isinstance(value, OpenAIWireResponse):
        return value
    if isinstance(value, Mapping):
        return OpenAIWireResponse(value)
    raise TransportContractError(
        "OpenAI requester must return an object payload or OpenAIWireResponse"
    )


def _http_error(
    response: OpenAIWireResponse,
    payload: dict[str, Any],
    provider_request_id: str | None,
) -> OpenAIProviderRequestError:
    error = payload.get("error")
    error_object = error if isinstance(error, dict) else {}
    headers = _lower_headers(response.headers)
    return OpenAIProviderRequestError(
        "OpenAI returned a non-success HTTP response",
        http_status=response.http_status,
        error_code=_optional_string(error_object.get("code")),
        error_type=_optional_string(error_object.get("type")),
        retry_after_seconds=_retry_after_seconds(headers.get("retry-after")),
        provider_request_id=provider_request_id,
    )


def _provider_request_id(
    response: OpenAIWireResponse, payload: dict[str, Any]
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
        raise TransportContractError("OpenAI wire value is not JSON serializable") from error


def _json_object(value: Any, label: str) -> dict[str, Any]:
    cloned = _json_clone(value)
    if not isinstance(cloned, dict):
        raise TransportContractError(f"{label} must be an object")
    return cloned


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TransportContractError(f"OpenAI {label} must be a string")
    return value


def _required_nonempty_string(value: Any, label: str) -> str:
    text = _required_string(value, label)
    if not text:
        raise TransportContractError(f"OpenAI {label} must be non-empty")
    return text


def _optional_nonempty_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _required_nonempty_string(value, label)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransportContractError(f"OpenAI {label} must be a non-negative integer")
    return value


def _optional_nonnegative_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _required_nonnegative_int(value, label)
