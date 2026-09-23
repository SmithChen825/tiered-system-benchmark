from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


TRANSPORT_CONTRACT_VERSION = "1.0.0"
SUBMIT_MARKER = "<SUBMIT_FIX>"
LOGICAL_TOOL_NAMES = frozenset(
    {
        "execute_bash",
        "read_file",
        "patch_file",
        "request_human_clarification",
    }
)


class WrapperError(RuntimeError):
    """Base class for expected wrapper failures."""


class WrapperConfigurationError(WrapperError):
    """Raised before a run starts when frozen configuration is incomplete."""


class WrapperInvariantError(WrapperError):
    """Raised when normalized provider data violates the common contract."""


class TransportInfrastructureError(WrapperError):
    """Provider transport failed outside the assigned task fault."""

    def __init__(
        self,
        detail: str,
        *,
        attempts: int = 1,
        attempt_records: tuple["TransportAttempt", ...] = (),
    ) -> None:
        super().__init__(detail)
        self.attempts = attempts
        self.attempt_records = attempt_records


class TransportContractError(WrapperError):
    """Adapter code violated the frozen normalized transport contract."""


class ToolInfrastructureError(WrapperError):
    """The shared tool executor itself could not operate."""


class ToolCommandTimeout(WrapperError):
    """An accepted execute_bash call reached the frozen command timeout."""

    def __init__(self, detail: str, *, output: str = "") -> None:
        super().__init__(detail)
        self.output = output


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    argument_error: str | None = None


@dataclass(frozen=True)
class ContextMessage:
    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class UsageDelta:
    input_tokens: int
    output_tokens: int
    monetary_cost: float | None = None
    currency: str | None = None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    provider_reported_total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts cannot be negative")
        for label, value in (
            ("cached_input_tokens", self.cached_input_tokens),
            ("reasoning_output_tokens", self.reasoning_output_tokens),
            ("provider_reported_total_tokens", self.provider_reported_total_tokens),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{label} cannot be negative")
        if (
            self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if (
            self.reasoning_output_tokens is not None
            and self.reasoning_output_tokens > self.output_tokens
        ):
            raise ValueError("reasoning_output_tokens cannot exceed output_tokens")
        if self.monetary_cost is not None and self.monetary_cost < 0:
            raise ValueError("Monetary cost cannot be negative")
        if (self.monetary_cost is None) != (self.currency is None):
            raise ValueError("Cost and currency must be provided together")


@dataclass(frozen=True)
class ModelTurn:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    raw_payload: dict[str, Any] = field(default_factory=dict)
    response_id: str | None = None
    usage: UsageDelta | None = None
    finish_reason: str = "completed"
    transport_attempts: tuple["TransportAttempt", ...] = ()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 2.0)
    maximum_retry_after_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if len(self.backoff_seconds) != self.max_attempts - 1:
            raise ValueError("backoff_seconds must contain one delay per possible retry")
        if any(value < 0 for value in self.backoff_seconds):
            raise ValueError("Retry delays cannot be negative")
        if self.maximum_retry_after_seconds < 0:
            raise ValueError("maximum_retry_after_seconds cannot be negative")


@dataclass(frozen=True)
class TransportPolicy:
    contract_version: str = TRANSPORT_CONTRACT_VERSION
    request_timeout_seconds: float = 120.0
    max_output_tokens: int = 4096
    temperature: float = 0.0
    tool_choice: str = "auto"
    parallel_tool_calls: bool = True
    stream: bool = False
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        if self.contract_version != TRANSPORT_CONTRACT_VERSION:
            raise ValueError("Unsupported transport contract version")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.temperature < 0:
            raise ValueError("temperature cannot be negative")
        if self.tool_choice != "auto":
            raise ValueError("The frozen shared tool choice is auto")
        if self.stream:
            raise ValueError("The frozen transport contract requires non-streaming calls")


@dataclass(frozen=True)
class TransportRequest:
    logical_request_id: str
    model_turn: int
    messages: tuple[ContextMessage, ...]
    tool_definitions: tuple[dict[str, Any], ...]
    policy: TransportPolicy

    def __post_init__(self) -> None:
        if not self.logical_request_id:
            raise ValueError("logical_request_id must be non-empty")
        if self.model_turn < 1:
            raise ValueError("model_turn must be positive")
        if not self.messages:
            raise ValueError("messages must be non-empty")
        if not self.tool_definitions:
            raise ValueError("tool_definitions must be non-empty")


@dataclass(frozen=True)
class TransportAttempt:
    attempt_number: int
    outcome: str
    elapsed_seconds: float
    error_kind: str | None = None
    http_status: int | None = None
    provider_error_code: str | None = None
    provider_request_id: str | None = None
    retry_delay_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        if self.outcome not in {"success", "retryable_error", "terminal_error"}:
            raise ValueError("Unsupported transport attempt outcome")
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds cannot be negative")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("http_status is outside the valid HTTP range")
        if self.retry_delay_seconds is not None and self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        if self.outcome == "success" and self.error_kind is not None:
            raise ValueError("Successful attempts cannot contain error_kind")
        if self.outcome == "retryable_error" and self.retry_delay_seconds is None:
            raise ValueError("Retryable attempts must record their retry delay")
        if self.outcome != "retryable_error" and self.retry_delay_seconds is not None:
            raise ValueError("Only retryable attempts may record a retry delay")


@dataclass(frozen=True)
class ToolExecutionResult:
    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelTransport(Protocol):
    provider_name: str
    contract_version: str

    def generate(self, request: TransportRequest) -> ModelTurn:
        """Return one normalized provider response."""


class LogicalToolExecutor(Protocol):
    def execute(
        self,
        call: ToolCall,
        *,
        workspace: Path,
        command_timeout_seconds: int,
    ) -> ToolExecutionResult:
        """Execute one accepted logical action against the isolated workspace."""


TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the isolated task workspace.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 4096}
            },
        },
    },
    {
        "name": "patch_file",
        "description": (
            "Apply a standard unified git diff to files in the isolated task workspace. "
            "The patch must include diff --git, ---, +++, and @@ headers."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["patch"],
            "properties": {
                "patch": {"type": "string", "minLength": 1, "maxLength": 1048576}
            },
        },
    },
    {
        "name": "execute_bash",
        "description": (
            "Execute one Bash command in the isolated task workspace sandbox. "
            "The default sandbox has no network or host-Docker access."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "minLength": 1, "maxLength": 16384}
            },
        },
    },
    {
        "name": "request_human_clarification",
        "description": "Submit one observable clarification request under the frozen protocol.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["request"],
            "properties": {
                "request": {"type": "string", "minLength": 1, "maxLength": 4096}
            },
        },
    },
)
