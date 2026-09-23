from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .contracts import (
    ContextMessage,
    ModelTurn,
    ToolCall,
    TransportAttempt,
    TransportContractError,
    TransportPolicy,
    TransportRequest,
    UsageDelta,
)


class TransportErrorKind(str, Enum):
    CONNECTION = "connection_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER = "server_error"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    QUOTA = "quota_or_billing"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTENT_POLICY = "content_policy"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN = "unknown"


class ErrorDisposition(str, Enum):
    RETRY = "retry"
    INVALIDATE = "invalidate"
    CONTRACT_ERROR = "contract_error"


@dataclass(frozen=True)
class ProviderError:
    http_status: int | None = None
    error_code: str | None = None
    error_type: str | None = None
    is_timeout: bool = False
    is_connection_error: bool = False
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("http_status is outside the valid HTTP range")
        if self.is_timeout and self.is_connection_error:
            raise ValueError("An error cannot be both timeout and connection_error")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative")


@dataclass(frozen=True)
class RetryDecision:
    kind: TransportErrorKind
    disposition: ErrorDisposition
    retry_delay_seconds: float | None
    reason: str


_QUOTA_CODES = frozenset(
    {
        "credit_balance_exhausted",
        "insufficient_quota",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "billing_not_active",
    }
)
_CONTENT_POLICY_CODES = frozenset(
    {"content_filter", "content_policy_violation", "safety_violation"}
)
_RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def classify_provider_error(error: ProviderError) -> TransportErrorKind:
    code = (error.error_code or "").casefold()
    error_type = (error.error_type or "").casefold()
    if error.is_timeout:
        return TransportErrorKind.TIMEOUT
    if error.is_connection_error:
        return TransportErrorKind.CONNECTION
    if error_type == TransportErrorKind.MALFORMED_RESPONSE.value:
        return TransportErrorKind.MALFORMED_RESPONSE
    if code in _QUOTA_CODES or "quota" in code or "billing" in code or "spend_limit" in code:
        return TransportErrorKind.QUOTA
    if code in _CONTENT_POLICY_CODES or "content_policy" in error_type:
        return TransportErrorKind.CONTENT_POLICY
    status = error.http_status
    if status == 401:
        return TransportErrorKind.AUTHENTICATION
    if status == 403:
        return TransportErrorKind.PERMISSION
    if status == 404:
        return TransportErrorKind.MODEL_UNAVAILABLE
    if status == 408:
        return TransportErrorKind.TIMEOUT
    if status in {409, 425}:
        return TransportErrorKind.SERVER
    if status == 429:
        return TransportErrorKind.RATE_LIMIT
    if status is not None and 500 <= status <= 599:
        return TransportErrorKind.SERVER
    if status is not None and 400 <= status <= 499:
        return TransportErrorKind.INVALID_REQUEST
    return TransportErrorKind.UNKNOWN


def decide_retry(
    error: ProviderError,
    *,
    attempt_number: int,
    policy: TransportPolicy,
) -> RetryDecision:
    if not 1 <= attempt_number <= policy.retry.max_attempts:
        raise ValueError("attempt_number is outside the frozen retry policy")
    kind = classify_provider_error(error)
    transient = (
        error.is_timeout
        or error.is_connection_error
        or error.http_status in _RETRYABLE_HTTP_STATUSES
    ) and kind not in {
        TransportErrorKind.QUOTA,
        TransportErrorKind.AUTHENTICATION,
        TransportErrorKind.PERMISSION,
        TransportErrorKind.INVALID_REQUEST,
        TransportErrorKind.MODEL_UNAVAILABLE,
        TransportErrorKind.CONTENT_POLICY,
    }
    if not transient:
        return RetryDecision(kind, ErrorDisposition.INVALIDATE, None, "non_retryable")
    if attempt_number >= policy.retry.max_attempts:
        return RetryDecision(kind, ErrorDisposition.INVALIDATE, None, "attempts_exhausted")
    retry_after = error.retry_after_seconds
    if (
        retry_after is not None
        and retry_after > policy.retry.maximum_retry_after_seconds
    ):
        return RetryDecision(
            kind,
            ErrorDisposition.INVALIDATE,
            None,
            "retry_after_exceeds_frozen_maximum",
        )
    frozen_delay = policy.retry.backoff_seconds[attempt_number - 1]
    delay = max(frozen_delay, retry_after or 0.0)
    return RetryDecision(kind, ErrorDisposition.RETRY, delay, "transient")


def normalize_tool_arguments(raw_arguments: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw_arguments, dict):
        try:
            json.dumps(raw_arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            return {}, "arguments_not_json_serializable"
        return raw_arguments, None
    if not isinstance(raw_arguments, str):
        return {}, "arguments_not_string_or_object"
    try:
        parsed = json.loads(raw_arguments)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, "arguments_invalid_json"
    if not isinstance(parsed, dict):
        return {}, "arguments_json_not_object"
    return parsed, None


def validate_transport_request(request: TransportRequest) -> None:
    if not isinstance(request, TransportRequest):
        raise TransportContractError("Transport request has the wrong type")
    if not isinstance(request.policy, TransportPolicy):
        raise TransportContractError("Transport request policy has the wrong type")
    validate_tool_definitions(request.tool_definitions)
    pending_calls: dict[str, str] = {}
    completed_calls: set[str] = set()
    for index, message in enumerate(request.messages):
        if not isinstance(message, ContextMessage):
            raise TransportContractError(f"Message {index} is not ContextMessage")
        if message.role not in {"system", "user", "assistant", "tool"}:
            raise TransportContractError(f"Unsupported message role: {message.role}")
        if not isinstance(message.content, str):
            raise TransportContractError(f"Message {index} content is not text")
        if message.role != "assistant" and message.tool_calls:
            raise TransportContractError("Only assistant messages may contain tool calls")
        if message.role == "assistant":
            for call in message.tool_calls:
                _validate_tool_call(call)
                if call.call_id in pending_calls or call.call_id in completed_calls:
                    raise TransportContractError(f"Duplicate call_id in context: {call.call_id}")
                pending_calls[call.call_id] = call.name
        if message.role == "tool":
            if not message.tool_call_id or not message.tool_name:
                raise TransportContractError("Tool messages require call ID and tool name")
            expected_name = pending_calls.get(message.tool_call_id)
            if expected_name is None:
                raise TransportContractError(
                    f"Tool result has no preceding call: {message.tool_call_id}"
                )
            if expected_name != message.tool_name:
                raise TransportContractError(
                    f"Tool result name disagrees for call: {message.tool_call_id}"
                )
            del pending_calls[message.tool_call_id]
            completed_calls.add(message.tool_call_id)
    if pending_calls:
        raise TransportContractError(
            "Context contains assistant tool calls without results: "
            + ", ".join(sorted(pending_calls))
        )


def validate_model_turn(turn: ModelTurn, *, require_attempts: bool = True) -> None:
    if not isinstance(turn, ModelTurn):
        raise TransportContractError("Provider adapter did not return ModelTurn")
    if not isinstance(turn.text, str):
        raise TransportContractError("Normalized response text must be a string")
    if turn.response_id is not None and not isinstance(turn.response_id, str):
        raise TransportContractError("response_id must be a string or null")
    if not turn.text and not turn.tool_calls:
        raise TransportContractError("Normalized response contains no text or tool calls")
    if turn.finish_reason not in {
        "completed",
        "tool_calls",
        "max_output_tokens",
        "content_filter",
        "refusal",
        "other",
    }:
        raise TransportContractError(f"Unsupported finish_reason: {turn.finish_reason}")
    try:
        json.dumps(turn.raw_payload, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise TransportContractError("raw_payload must be JSON serializable") from error
    if turn.usage is not None:
        if not isinstance(turn.usage, UsageDelta):
            raise TransportContractError("usage must be UsageDelta or null")
    seen_calls: set[str] = set()
    for call in turn.tool_calls:
        _validate_tool_call(call)
        if call.call_id in seen_calls:
            raise TransportContractError(f"Duplicate call_id in response: {call.call_id}")
        seen_calls.add(call.call_id)
    if require_attempts:
        if not turn.transport_attempts:
            raise TransportContractError("Provider adapter omitted transport attempts")
        _validate_attempt_sequence(turn.transport_attempts, final_success=True)


def validate_tool_definitions(definitions: tuple[dict[str, Any], ...]) -> None:
    names: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict):
            raise TransportContractError("Tool definition is not an object")
        if set(definition) != {"name", "description", "input_schema"}:
            raise TransportContractError("Tool definition has unexpected fields")
        name = definition.get("name")
        description = definition.get("description")
        schema = definition.get("input_schema")
        if not isinstance(name, str) or not name or name in names:
            raise TransportContractError(f"Invalid or duplicate tool name: {name!r}")
        names.add(name)
        if not isinstance(description, str) or not description:
            raise TransportContractError(f"Tool {name} lacks a description")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise TransportContractError(f"Tool {name} schema must be an object")
        properties = schema.get("properties")
        required = schema.get("required")
        if schema.get("additionalProperties") is not False:
            raise TransportContractError(f"Tool {name} must reject additional properties")
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise TransportContractError(f"Tool {name} properties/required are invalid")
        if set(required) != set(properties):
            raise TransportContractError(f"Tool {name} must require every property")


def policy_sha256(policy: TransportPolicy) -> str:
    encoded = json.dumps(
        asdict(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_sha256(request: TransportRequest) -> str:
    validate_transport_request(request)
    value = {
        "logical_request_id": request.logical_request_id,
        "model_turn": request.model_turn,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "tool_call_id": message.tool_call_id,
                "tool_name": message.tool_name,
                "tool_calls": [
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "argument_error": call.argument_error,
                    }
                    for call in message.tool_calls
                ],
            }
            for message in request.messages
        ],
        "tool_definitions": request.tool_definitions,
        "policy": asdict(request.policy),
    }
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attempt_records_json(attempts: tuple[TransportAttempt, ...]) -> list[dict[str, Any]]:
    _validate_attempt_sequence(attempts, final_success=None)
    return [asdict(attempt) for attempt in attempts]


def _validate_tool_call(call: ToolCall) -> None:
    if not isinstance(call, ToolCall) or not call.call_id or not call.name:
        raise TransportContractError("Tool call ID and name must be non-empty")
    if not isinstance(call.arguments, dict):
        raise TransportContractError("Tool call arguments must be an object")
    try:
        json.dumps(call.arguments, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise TransportContractError("Tool call arguments are not JSON serializable") from error
    if call.argument_error is not None:
        if call.argument_error not in {
            "arguments_not_json_serializable",
            "arguments_not_string_or_object",
            "arguments_invalid_json",
            "arguments_json_not_object",
        }:
            raise TransportContractError("Unknown tool argument error code")
        if call.arguments:
            raise TransportContractError("Malformed tool calls must normalize to empty arguments")


def _validate_attempt_sequence(
    attempts: tuple[TransportAttempt, ...], *, final_success: bool | None
) -> None:
    if not attempts:
        raise TransportContractError("Transport attempt sequence is empty")
    for expected, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, TransportAttempt):
            raise TransportContractError("Attempt sequence contains an invalid value")
        if attempt.attempt_number != expected:
            raise TransportContractError("Transport attempt numbers must be contiguous")
        if expected < len(attempts) and attempt.outcome != "retryable_error":
            raise TransportContractError("Only retryable errors may precede another attempt")
    if final_success is True and attempts[-1].outcome != "success":
        raise TransportContractError("Successful model turn must end in a successful attempt")
    if final_success is False and attempts[-1].outcome != "terminal_error":
        raise TransportContractError("Failed transport must end in a terminal error")
