from __future__ import annotations

import json
import math
import os
import socket
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ...paid_stage_meter import (
    OPENAI,
    QWEN,
    CombinedPaidStageMeter,
    PaidStageMeterError,
    PaidStageStopped,
    estimate_openai_response_cost_usd,
    project_openai_request_cost_usd,
)
from ..contracts import TransportPolicy
from ..transport_contract import ErrorDisposition, decide_retry
from .openai_responses import (
    OpenAIProviderRequestError,
    OpenAIWireResponse,
    _http_error as _openai_http_error,
)
from .qwen_vllm import (
    QwenProviderRequestError,
    QwenWireResponse,
    _http_error as _qwen_http_error,
)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
QWEN_CHAT_COMPLETIONS_ROUTE = "/v1/chat/completions"
LIVE_PROVIDER_AUTHORIZATION_ENV = "TSB_LIVE_PROVIDER_AUTHORIZATION"
LIVE_PROVIDER_AUTHORIZATION_VALUE = "I_AUTHORIZE_PAID_PROVIDER_CALLS"
OPENAI_API_KEY_ENV = "TSB_OPENAI_API_KEY"
OPENAI_ORGANIZATION_ENV = "TSB_OPENAI_ORGANIZATION_ID"
OPENAI_PROJECT_ENV = "TSB_OPENAI_PROJECT_ID"
QWEN_ENDPOINT_URL_ENV = "TSB_QWEN_ENDPOINT_URL"
QWEN_API_TOKEN_ENV = "TSB_QWEN_API_TOKEN"
PAID_STAGE_METER_PATH_ENV = "TSB_PAID_STAGE_METER_PATH"
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
USER_AGENT = "tsb-provider-bridge/1.0"
PAID_STAGE_PHASES = frozenset({"live_gate", "pilot", "main"})


UrlOpener = Callable[..., Any]


@dataclass(frozen=True)
class _DecodedResponse:
    payload: Mapping[str, Any]
    http_status: int
    headers: Mapping[str, str]


class _BridgeFailure(RuntimeError):
    def __init__(
        self,
        detail: str,
        *,
        http_status: int | None = None,
        error_type: str | None = None,
        provider_request_id: str | None = None,
        is_timeout: bool = False,
        is_connection_error: bool = False,
    ) -> None:
        super().__init__(detail)
        self.http_status = http_status
        self.error_type = error_type
        self.provider_request_id = provider_request_id
        self.is_timeout = is_timeout
        self.is_connection_error = is_connection_error


class _BearerJsonClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        extra_headers: Mapping[str, str] | None = None,
        opener: UrlOpener = urlopen,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._url = url
        self._token = _validated_secret(token, "provider token")
        self._extra_headers = {
            _validated_header_name(name): _validated_header_value(value, name)
            for name, value in (extra_headers or {}).items()
        }
        if not callable(opener):
            raise TypeError("opener must be callable")
        if isinstance(max_response_bytes, bool) or not isinstance(
            max_response_bytes, int
        ) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        self._opener = opener
        self._max_response_bytes = max_response_bytes

    @property
    def url(self) -> str:
        return self._url

    def post(self, payload: Mapping[str, Any], timeout: float) -> _DecodedResponse:
        timeout = _validated_timeout(timeout)
        try:
            body = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise _BridgeFailure(
                "Provider request payload is not JSON serializable",
                error_type="invalid_request_payload",
            ) from error
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **self._extra_headers,
        }
        request = Request(self._url, data=body, headers=headers, method="POST")
        try:
            response = self._opener(request, timeout=timeout)
        except HTTPError as error:
            return self._decode_http_error(error)
        except (TimeoutError, socket.timeout) as error:
            raise _BridgeFailure(
                "Provider request timed out", is_timeout=True
            ) from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise _BridgeFailure(
                    "Provider request timed out", is_timeout=True
                ) from error
            raise _BridgeFailure(
                "Provider connection failed", is_connection_error=True
            ) from error
        except OSError as error:
            raise _BridgeFailure(
                "Provider connection failed", is_connection_error=True
            ) from error
        return self._decode_success(response)

    def _decode_success(self, response: Any) -> _DecodedResponse:
        try:
            status = _response_status(response)
            headers = _response_headers(response)
            request_id = _request_id(headers)
            try:
                raw = _bounded_read(response, self._max_response_bytes)
            except _BridgeFailure as error:
                raise _BridgeFailure(
                    str(error),
                    http_status=status,
                    error_type=error.error_type,
                    provider_request_id=request_id,
                    is_timeout=error.is_timeout,
                    is_connection_error=error.is_connection_error,
                ) from error
        finally:
            _close_response(response)
        payload = _decode_json_object(
            raw,
            http_status=status,
            provider_request_id=request_id,
        )
        return _DecodedResponse(payload, status, headers)

    def _decode_http_error(self, error: HTTPError) -> _DecodedResponse:
        try:
            status = int(error.code)
            headers = _response_headers(error)
            raw = _bounded_read(error, self._max_response_bytes)
            payload = _decode_json_object(
                raw,
                http_status=status,
                provider_request_id=_request_id(headers),
            )
        except _BridgeFailure:
            payload = {
                "error": {
                    "type": "invalid_error_response",
                    "code": None,
                }
            }
        finally:
            _close_response(error)
        return _DecodedResponse(payload, status, headers)


class OpenAIResponsesHttpRequester:
    """Fail-closed HTTPS requester for the frozen OpenAI Responses adapter."""

    def __init__(
        self,
        api_key: str,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        opener: UrlOpener = urlopen,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        paid_stage_meter: CombinedPaidStageMeter | None = None,
        allow_unmetered_for_testing: bool = False,
        paid_stage_phase: str | None = None,
    ) -> None:
        if paid_stage_meter is None and not allow_unmetered_for_testing:
            raise RuntimeError(
                "Live OpenAI requester requires a paid-stage meter; "
                "unmetered construction is test-only"
            )
        self._paid_stage_phase = _paid_stage_phase(
            paid_stage_phase, meter_is_bound=paid_stage_meter is not None
        )
        extra_headers: dict[str, str] = {}
        if organization_id is not None:
            extra_headers["OpenAI-Organization"] = organization_id
        if project_id is not None:
            extra_headers["OpenAI-Project"] = project_id
        self._client = _BearerJsonClient(
            url=OPENAI_RESPONSES_URL,
            token=api_key,
            extra_headers=extra_headers,
            opener=opener,
            max_response_bytes=max_response_bytes,
        )
        self._paid_stage_meter = paid_stage_meter
        self.requires_paid_meter_context = paid_stage_meter is not None

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        opener: UrlOpener = urlopen,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        paid_stage_meter: CombinedPaidStageMeter | None = None,
        paid_stage_phase: str | None = None,
    ) -> OpenAIResponsesHttpRequester:
        values = os.environ if environ is None else environ
        _require_live_authorization(values)
        meter = _required_paid_stage_meter(values, paid_stage_meter)
        phase = _paid_stage_phase(paid_stage_phase, meter_is_bound=True)
        return cls(
            _required_environment_value(values, OPENAI_API_KEY_ENV),
            organization_id=_optional_environment_value(
                values, OPENAI_ORGANIZATION_ENV
            ),
            project_id=_optional_environment_value(values, OPENAI_PROJECT_ENV),
            opener=opener,
            max_response_bytes=max_response_bytes,
            paid_stage_meter=meter,
            paid_stage_phase=phase,
        )

    def __call__(self, payload: dict[str, Any], timeout: float) -> OpenAIWireResponse:
        if self._paid_stage_meter is not None:
            raise OpenAIProviderRequestError(
                "Metered OpenAI requester requires logical request context",
                error_type="paid_stage_meter_stopped",
            )
        return self._request(payload, timeout)

    def _request(self, payload: dict[str, Any], timeout: float) -> OpenAIWireResponse:
        try:
            response = self._client.post(payload, timeout)
        except _BridgeFailure as error:
            raise OpenAIProviderRequestError(
                str(error),
                http_status=error.http_status,
                error_type=error.error_type,
                provider_request_id=error.provider_request_id,
                is_timeout=error.is_timeout,
                is_connection_error=error.is_connection_error,
            ) from error
        return OpenAIWireResponse(
            response.payload,
            http_status=response.http_status,
            headers=response.headers,
        )

    def request_with_meter_context(
        self,
        payload: dict[str, Any],
        timeout: float,
        *,
        logical_request_id: str,
        attempt_number: int,
        transport_policy: TransportPolicy,
    ) -> OpenAIWireResponse:
        if self._paid_stage_meter is None:
            raise OpenAIProviderRequestError(
                "OpenAI paid-stage meter is not bound",
                error_type="paid_stage_meter_stopped",
            )
        action_id = f"openai:{logical_request_id}:http_attempt:{attempt_number}"
        projected = project_openai_request_cost_usd(payload)
        try:
            return self._paid_stage_meter.execute(
                action_id=action_id,
                provider=OPENAI,
                projected_increment_usd=projected,
                operation=lambda: self._request(payload, timeout),
                actual_increment=lambda wire: (
                    estimate_openai_response_cost_usd(wire.payload)
                    if 200 <= wire.http_status <= 299
                    else projected
                ),
                response_succeeded=lambda wire: 200 <= wire.http_status <= 299,
                operation_failure_stops_stage=lambda error: self._failure_stops_stage(
                    error, attempt_number, transport_policy
                ),
                response_failure_stops_stage=lambda wire: self._failure_stops_stage(
                    _openai_http_error(wire, wire.payload, None),
                    attempt_number,
                    transport_policy,
                ),
            )
        except PaidStageMeterError as error:
            raise OpenAIProviderRequestError(
                "OpenAI paid action stopped by the shared meter",
                error_type="paid_stage_meter_stopped",
            ) from error

    def _failure_stops_stage(
        self,
        error: BaseException,
        attempt_number: int,
        policy: TransportPolicy,
    ) -> bool:
        if self._paid_stage_phase == "live_gate":
            return True
        if not isinstance(error, OpenAIProviderRequestError):
            return True
        decision = decide_retry(
            error.provider_error, attempt_number=attempt_number, policy=policy
        )
        return decision.disposition is not ErrorDisposition.RETRY

    def __repr__(self) -> str:
        return (
            "OpenAIResponsesHttpRequester("
            f"url={OPENAI_RESPONSES_URL!r}, api_key=<redacted>)"
        )


class QwenVllmHttpRequester:
    """Fail-closed HTTPS requester for the reviewed HF/vLLM Endpoint."""

    def __init__(
        self,
        endpoint_url: str,
        api_token: str,
        *,
        opener: UrlOpener = urlopen,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        paid_stage_meter: CombinedPaidStageMeter | None = None,
        allow_unmetered_for_testing: bool = False,
        paid_stage_phase: str | None = None,
    ) -> None:
        if paid_stage_meter is None and not allow_unmetered_for_testing:
            raise RuntimeError(
                "Live Qwen requester requires a paid-stage meter; "
                "unmetered construction is test-only"
            )
        self._paid_stage_phase = _paid_stage_phase(
            paid_stage_phase, meter_is_bound=paid_stage_meter is not None
        )
        self._url = qwen_chat_completions_url(endpoint_url)
        self._client = _BearerJsonClient(
            url=self._url,
            token=api_token,
            opener=opener,
            max_response_bytes=max_response_bytes,
        )
        self._paid_stage_meter = paid_stage_meter
        self.requires_paid_meter_context = paid_stage_meter is not None

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        opener: UrlOpener = urlopen,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        paid_stage_meter: CombinedPaidStageMeter | None = None,
        paid_stage_phase: str | None = None,
    ) -> QwenVllmHttpRequester:
        values = os.environ if environ is None else environ
        _require_live_authorization(values)
        meter = _required_paid_stage_meter(values, paid_stage_meter)
        phase = _paid_stage_phase(paid_stage_phase, meter_is_bound=True)
        return cls(
            _required_environment_value(values, QWEN_ENDPOINT_URL_ENV),
            _required_environment_value(values, QWEN_API_TOKEN_ENV),
            opener=opener,
            max_response_bytes=max_response_bytes,
            paid_stage_meter=meter,
            paid_stage_phase=phase,
        )

    def __call__(self, payload: dict[str, Any], timeout: float) -> QwenWireResponse:
        if self._paid_stage_meter is not None:
            raise QwenProviderRequestError(
                "Metered Qwen requester requires logical request context",
                error_type="paid_stage_meter_stopped",
            )
        return self._request(payload, timeout)

    def _request(self, payload: dict[str, Any], timeout: float) -> QwenWireResponse:
        try:
            response = self._client.post(payload, timeout)
        except _BridgeFailure as error:
            raise QwenProviderRequestError(
                str(error),
                http_status=error.http_status,
                error_type=error.error_type,
                provider_request_id=error.provider_request_id,
                is_timeout=error.is_timeout,
                is_connection_error=error.is_connection_error,
            ) from error
        return QwenWireResponse(
            response.payload,
            http_status=response.http_status,
            headers=response.headers,
        )

    def request_with_meter_context(
        self,
        payload: dict[str, Any],
        timeout: float,
        *,
        logical_request_id: str,
        attempt_number: int,
        transport_policy: TransportPolicy,
    ) -> QwenWireResponse:
        if self._paid_stage_meter is None:
            raise QwenProviderRequestError(
                "Qwen paid-stage meter is not bound",
                error_type="paid_stage_meter_stopped",
            )
        action_id = f"qwen:{logical_request_id}:http_attempt:{attempt_number}"
        try:
            return self._paid_stage_meter.execute(
                action_id=action_id,
                provider=QWEN,
                projected_increment_usd=0,
                operation=lambda: self._request(payload, timeout),
                actual_increment=lambda _wire: 0,
                response_succeeded=lambda wire: 200 <= wire.http_status <= 299,
                require_qwen_runtime=True,
                operation_failure_stops_stage=lambda error: self._failure_stops_stage(
                    error, attempt_number, transport_policy
                ),
                response_failure_stops_stage=lambda wire: self._failure_stops_stage(
                    _qwen_http_error(wire, wire.payload, None),
                    attempt_number,
                    transport_policy,
                ),
            )
        except PaidStageMeterError as error:
            raise QwenProviderRequestError(
                "Qwen paid action stopped by the shared meter",
                error_type="paid_stage_meter_stopped",
            ) from error

    def _failure_stops_stage(
        self,
        error: BaseException,
        attempt_number: int,
        policy: TransportPolicy,
    ) -> bool:
        if self._paid_stage_phase == "live_gate":
            return True
        if not isinstance(error, QwenProviderRequestError):
            return True
        decision = decide_retry(
            error.provider_error, attempt_number=attempt_number, policy=policy
        )
        return decision.disposition is not ErrorDisposition.RETRY

    def __repr__(self) -> str:
        return f"QwenVllmHttpRequester(url={self._url!r}, api_token=<redacted>)"


def qwen_chat_completions_url(endpoint_url: str) -> str:
    if not isinstance(endpoint_url, str) or not endpoint_url:
        raise ValueError("Qwen Endpoint URL must be a non-empty string")
    if endpoint_url != endpoint_url.strip():
        raise ValueError("Qwen Endpoint URL must not contain surrounding whitespace")
    parts = urlsplit(endpoint_url)
    if parts.scheme.casefold() != "https":
        raise ValueError("Qwen Endpoint URL must use HTTPS")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Qwen Endpoint URL must not contain user information")
    if parts.query or parts.fragment:
        raise ValueError("Qwen Endpoint URL must not contain a query or fragment")
    hostname = (parts.hostname or "").casefold()
    if not hostname.endswith(".endpoints.huggingface.cloud"):
        raise ValueError(
            "Qwen Endpoint URL host must end with .endpoints.huggingface.cloud"
        )
    if parts.port not in {None, 443}:
        raise ValueError("Qwen Endpoint URL must use the default HTTPS port")
    base_path = parts.path.rstrip("/")
    if base_path.endswith(QWEN_CHAT_COMPLETIONS_ROUTE):
        path = base_path
    else:
        path = f"{base_path}{QWEN_CHAT_COMPLETIONS_ROUTE}"
    return urlunsplit(("https", parts.netloc, path, "", ""))


def _require_live_authorization(environ: Mapping[str, str]) -> None:
    value = environ.get(LIVE_PROVIDER_AUTHORIZATION_ENV)
    if value != LIVE_PROVIDER_AUTHORIZATION_VALUE:
        raise RuntimeError(
            f"{LIVE_PROVIDER_AUTHORIZATION_ENV} must equal the explicit live-call "
            "authorization value before credentials are loaded"
        )


def _required_paid_stage_meter(
    environ: Mapping[str, str], supplied: CombinedPaidStageMeter | None
) -> CombinedPaidStageMeter:
    meter = supplied
    if meter is None:
        path = environ.get(PAID_STAGE_METER_PATH_ENV)
        if path is None:
            raise RuntimeError(
                f"Required environment variable is missing: {PAID_STAGE_METER_PATH_ENV}"
            )
        if not isinstance(path, str) or not path or path != path.strip():
            raise RuntimeError(f"Invalid environment value: {PAID_STAGE_METER_PATH_ENV}")
        meter = CombinedPaidStageMeter(path)
    try:
        meter.snapshot()
    except PaidStageStopped:
        raise
    except PaidStageMeterError as error:
        raise RuntimeError("Paid-stage meter is not safely readable") from error
    return meter


def _paid_stage_phase(value: str | None, *, meter_is_bound: bool) -> str | None:
    if not meter_is_bound:
        if value is not None:
            raise ValueError("paid_stage_phase requires a paid-stage meter")
        return None
    if value not in PAID_STAGE_PHASES:
        raise ValueError(f"paid_stage_phase must be one of {sorted(PAID_STAGE_PHASES)}")
    return value


def _required_environment_value(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if value is None:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return _validated_secret(value, name)


def _optional_environment_value(
    environ: Mapping[str, str], name: str
) -> str | None:
    value = environ.get(name)
    if value is None:
        return None
    return _validated_header_value(value, name)


def _validated_secret(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if value != value.strip() or not all("!" <= character <= "~" for character in value):
        raise ValueError(
            f"{label} must contain only printable ASCII characters without whitespace"
        )
    return value


def _validated_header_name(name: str) -> str:
    if not isinstance(name, str) or not name or any(
        character in name for character in "\r\n:\0"
    ):
        raise ValueError("HTTP header name is invalid")
    return name


def _validated_header_value(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if value != value.strip() or not all("!" <= character <= "~" for character in value):
        raise ValueError(
            f"{label} must contain only printable ASCII characters without whitespace"
        )
    return value


def _validated_timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout must be a positive finite number")
    timeout = float(value)
    if timeout <= 0 or not math.isfinite(timeout):
        raise ValueError("timeout must be a positive finite number")
    return timeout


def _response_status(response: Any) -> int:
    value = getattr(response, "status", None)
    if value is None and hasattr(response, "getcode"):
        value = response.getcode()
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        raise _BridgeFailure(
            "Provider response omitted a valid HTTP status",
            error_type="malformed_response",
        )
    return value


def _response_headers(response: Any) -> dict[str, str]:
    value = getattr(response, "headers", None)
    if value is None:
        return {}
    if isinstance(value, Message) or hasattr(value, "items"):
        return {str(name): str(item) for name, item in value.items()}
    raise _BridgeFailure(
        "Provider response headers are malformed",
        error_type="malformed_response",
    )


def _bounded_read(response: Any, maximum: int) -> bytes:
    try:
        raw = response.read(maximum + 1)
    except (TimeoutError, socket.timeout) as error:
        raise _BridgeFailure("Provider response timed out", is_timeout=True) from error
    except OSError as error:
        raise _BridgeFailure(
            "Provider response read failed", is_connection_error=True
        ) from error
    if not isinstance(raw, bytes):
        raise _BridgeFailure(
            "Provider response body is not bytes",
            error_type="malformed_response",
        )
    if len(raw) > maximum:
        raise _BridgeFailure(
            "Provider response exceeded the configured byte limit",
            error_type="malformed_response",
        )
    return raw


def _decode_json_object(
    raw: bytes,
    *,
    http_status: int,
    provider_request_id: str | None,
) -> Mapping[str, Any]:
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _BridgeFailure(
            "Provider response was not valid UTF-8 JSON",
            http_status=http_status,
            error_type="malformed_response",
            provider_request_id=provider_request_id,
        ) from error
    if not isinstance(value, dict):
        raise _BridgeFailure(
            "Provider response JSON was not an object",
            http_status=http_status,
            error_type="malformed_response",
            provider_request_id=provider_request_id,
        )
    return value


def _request_id(headers: Mapping[str, str]) -> str | None:
    lowered = {str(name).casefold(): str(value) for name, value in headers.items()}
    value = lowered.get("x-request-id")
    return value if value else None


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()
