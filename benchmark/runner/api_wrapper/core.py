from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..common import ARTIFACT_PATHS, load_json, write_json
from .context import ConversationContext
from .contracts import (
    LOGICAL_TOOL_NAMES,
    SUBMIT_MARKER,
    TOOL_DEFINITIONS,
    TRANSPORT_CONTRACT_VERSION,
    LogicalToolExecutor,
    ModelTransport,
    ModelTurn,
    ToolCall,
    ToolCommandTimeout,
    ToolExecutionResult,
    ToolInfrastructureError,
    TransportContractError,
    TransportInfrastructureError,
    TransportPolicy,
    TransportRequest,
    UsageDelta,
    WrapperConfigurationError,
    WrapperInvariantError,
)
from .transport_contract import (
    attempt_records_json,
    policy_sha256,
    request_sha256,
    validate_model_turn,
    validate_transport_request,
)


@dataclass(frozen=True)
class WrapperSettings:
    max_context_characters: int | None = None
    max_model_turns: int = 1000
    transport_policy: TransportPolicy = TransportPolicy()

    def __post_init__(self) -> None:
        if self.max_context_characters is not None and self.max_context_characters < 1:
            raise ValueError("max_context_characters must be positive or null")
        if self.max_model_turns < 1:
            raise ValueError("max_model_turns must be positive")


@dataclass(frozen=True)
class RunOutcome:
    lifecycle_state: str
    stop_reason: str
    actions_executed: int
    model_turns: int
    elapsed_seconds: float


class _SystemClock:
    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def monotonic() -> float:
        return time.monotonic()


class _UsageAccumulator:
    def __init__(self) -> None:
        self.complete = True
        self.saw_turn = False
        self.input_tokens = 0
        self.output_tokens = 0
        self.monetary_cost: float | None = None
        self.currency: str | None = None

    def add(self, usage: UsageDelta | None) -> None:
        self.saw_turn = True
        if usage is None:
            self.complete = False
            return
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        if usage.monetary_cost is not None:
            if self.currency not in {None, usage.currency}:
                raise WrapperInvariantError("Provider usage changed currency during a run")
            self.currency = usage.currency
            self.monetary_cost = (self.monetary_cost or 0) + usage.monetary_cost

    def apply(self, metadata: dict[str, Any]) -> None:
        if not self.saw_turn or not self.complete:
            metadata["usage"] = {
                "status": "unavailable",
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "monetary_cost": None,
                "currency": None,
            }
            return
        metadata["usage"] = {
            "status": "available",
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "monetary_cost": self.monetary_cost,
            "currency": self.currency,
        }


class ApiAgentRunner:
    def __init__(
        self,
        *,
        transport: ModelTransport,
        tool_executor: LogicalToolExecutor,
        system_prompt: str,
        settings: WrapperSettings | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.transport = transport
        self.tool_executor = tool_executor
        self.system_prompt = system_prompt
        self.settings = settings or WrapperSettings()
        self._now = now or _SystemClock.now
        self._monotonic = monotonic or _SystemClock.monotonic

    def run(self, evidence_directory: Path, workspace: Path) -> RunOutcome:
        evidence_directory = evidence_directory.resolve()
        workspace = workspace.resolve()
        metadata_path = evidence_directory / "metadata.json"
        metadata = load_json(metadata_path)
        self._preflight(metadata, evidence_directory, workspace)

        task_prompt = (evidence_directory / ARTIFACT_PATHS["task_prompt"]).read_text(
            encoding="utf-8"
        )
        context = ConversationContext(
            self.system_prompt,
            task_prompt,
            max_characters=self.settings.max_context_characters,
        )
        evidence = _EvidenceWriter(evidence_directory, self._now)
        evidence.start(task_prompt, self.transport.provider_name)
        clarification_events: list[dict[str, Any]] = []
        usage = _UsageAccumulator()
        seen_call_ids: set[str] = set()
        actions = 0
        turns = 0
        consecutive_no_action_responses = 0
        started_monotonic = self._monotonic()
        started_at = self._timestamp()

        metadata["lifecycle_state"] = "running"
        metadata["validity_status"] = "pending"
        metadata["timing"] = {
            "started_at": started_at,
            "ended_at": None,
            "elapsed_seconds": None,
        }
        self._atomic_metadata(metadata_path, metadata)
        evidence.decision(
            "run_started",
            provider=self.transport.provider_name,
            action_limit=metadata["limits"]["api_action_limit"],
            command_timeout_seconds=metadata["limits"]["command_timeout_seconds"],
            task_wall_clock_seconds=metadata["limits"]["task_wall_clock_seconds"],
            consecutive_no_action_response_limit=metadata["limits"][
                "consecutive_no_action_response_limit"
            ],
        )

        stop_state: str | None = None
        stop_reason: str | None = None
        stop_detail: str | None = None
        try:
            while stop_state is None:
                if turns >= self.settings.max_model_turns:
                    raise WrapperInvariantError(
                        f"Internal safety limit reached at {turns} model turns"
                    )
                if self._wall_clock_reached(metadata, started_monotonic):
                    stop_state = "suspended"
                    stop_reason = "task_wall_clock_limit"
                    stop_detail = "Task wall-clock limit reached before the next model turn."
                    break

                snapshot = context.snapshot()
                transport_request = TransportRequest(
                    logical_request_id=f"{metadata['run_id']}:turn:{turns + 1}",
                    model_turn=turns + 1,
                    messages=snapshot.messages,
                    tool_definitions=TOOL_DEFINITIONS,
                    policy=self.settings.transport_policy,
                )
                validate_transport_request(transport_request)
                evidence.decision(
                    "context_snapshot",
                    model_turn=turns + 1,
                    message_count=len(snapshot.messages),
                    character_count=snapshot.character_count,
                    retained_turns=snapshot.retained_turns,
                    dropped_turns=snapshot.dropped_turns,
                )
                evidence.decision(
                    "transport_request",
                    logical_request_id=transport_request.logical_request_id,
                    model_turn=transport_request.model_turn,
                    contract_version=TRANSPORT_CONTRACT_VERSION,
                    policy_sha256=policy_sha256(transport_request.policy),
                    request_sha256=request_sha256(transport_request),
                )
                try:
                    turn = self.transport.generate(transport_request)
                except TransportInfrastructureError:
                    raise
                except TransportContractError:
                    raise
                except Exception as error:
                    raise TransportInfrastructureError(
                        f"Transport {self.transport.provider_name} failed: "
                        f"{type(error).__name__}: {error}"
                    ) from error
                turns += 1
                self._validate_turn(turn, seen_call_ids)
                usage.add(turn.usage)
                evidence.raw_response(turns, self.transport.provider_name, turn)
                evidence.assistant(turn.text, turn.tool_calls)
                context.append_model_turn(turn)

                if self._wall_clock_reached(metadata, started_monotonic):
                    stop_state = "suspended"
                    stop_reason = "task_wall_clock_limit"
                    stop_detail = "Task wall-clock limit reached while awaiting a model response."
                    break
                if SUBMIT_MARKER in turn.text:
                    stop_state = "submitted"
                    stop_reason = "submitted"
                    stop_detail = "Exact <SUBMIT_FIX> marker observed in assistant text."
                    evidence.decision(
                        "submission_detected",
                        model_turn=turns,
                        ignored_tool_calls=len(turn.tool_calls),
                    )
                    break

                accepted_this_turn = 0
                for call in turn.tool_calls:
                    if self._wall_clock_reached(metadata, started_monotonic):
                        stop_state = "suspended"
                        stop_reason = "task_wall_clock_limit"
                        stop_detail = "Task wall-clock limit reached before a tool action."
                        break
                    if call.name not in LOGICAL_TOOL_NAMES:
                        result = ToolExecutionResult(
                            f"Unsupported logical tool: {call.name}", is_error=True
                        )
                        evidence.decision(
                            "tool_call_rejected",
                            call_id=call.call_id,
                            tool_name=call.name,
                            reason="unknown_tool",
                        )
                        context.append_tool_result(call.call_id, call.name, result)
                        evidence.tool_result(call, result)
                        continue

                    action_limit = metadata["limits"]["api_action_limit"]
                    if actions >= action_limit:
                        stop_state = "suspended"
                        stop_reason = "api_action_limit"
                        stop_detail = (
                            f"API action limit {action_limit} reached before call "
                            f"{call.call_id}."
                        )
                        evidence.decision(
                            "tool_call_blocked_by_limit",
                            call_id=call.call_id,
                            tool_name=call.name,
                            actions_executed=actions,
                        )
                        break

                    actions += 1
                    accepted_this_turn += 1
                    evidence.decision(
                        "tool_call_accepted",
                        call_id=call.call_id,
                        tool_name=call.name,
                        action_number=actions,
                        arguments=call.arguments,
                    )
                    if call.name == "request_human_clarification":
                        self._record_clarification_request(
                            metadata, clarification_events, call, actions
                        )
                    try:
                        result = self.tool_executor.execute(
                            call,
                            workspace=workspace,
                            command_timeout_seconds=metadata["limits"][
                                "command_timeout_seconds"
                            ],
                        )
                    except ToolCommandTimeout as error:
                        result = ToolExecutionResult(error.output or str(error), is_error=True)
                        context.append_tool_result(call.call_id, call.name, result)
                        evidence.tool_result(call, result)
                        stop_state = "suspended"
                        stop_reason = "command_timeout"
                        stop_detail = str(error)
                        break
                    except ToolInfrastructureError:
                        raise
                    except Exception as error:
                        raise WrapperInvariantError(
                            f"Tool executor failed for {call.name}: "
                            f"{type(error).__name__}: {error}"
                        ) from error
                    if not isinstance(result, ToolExecutionResult):
                        raise WrapperInvariantError(
                            f"Tool executor returned invalid result for {call.name}"
                        )
                    if call.name == "request_human_clarification":
                        self._record_clarification_decision(
                            metadata, clarification_events, call, result
                        )
                    context.append_tool_result(call.call_id, call.name, result)
                    evidence.tool_result(call, result)

                if stop_state is not None:
                    continue
                if accepted_this_turn:
                    consecutive_no_action_responses = 0
                    continue
                consecutive_no_action_responses += 1
                no_action_limit = metadata["limits"][
                    "consecutive_no_action_response_limit"
                ]
                evidence.decision(
                    "no_action_response",
                    model_turn=turns,
                    consecutive_count=consecutive_no_action_responses,
                    limit=no_action_limit,
                    returned_tool_calls=len(turn.tool_calls),
                )
                if consecutive_no_action_responses >= no_action_limit:
                    stop_state = "suspended"
                    stop_reason = "protocol_no_progress_limit"
                    stop_detail = (
                        f"No accepted logical tool call or submit marker was observed in "
                        f"{no_action_limit} consecutive model responses."
                    )
                    evidence.decision(
                        "no_action_limit_reached",
                        model_turn=turns,
                        consecutive_count=consecutive_no_action_responses,
                        limit=no_action_limit,
                    )

            if stop_state is None or stop_reason is None:
                raise WrapperInvariantError("Run loop exited without a stopping transition")
        except TransportInfrastructureError as error:
            stop_state = "invalidated"
            stop_reason = "infrastructure_failure"
            stop_detail = str(error)
            evidence.raw_error(
                "transport_failure",
                detail=str(error),
                attempts=error.attempts,
                attempt_records=attempt_records_json(error.attempt_records)
                if error.attempt_records
                else [],
            )
            evidence.decision(
                "run_exception",
                classification="infrastructure_failure",
                detail=str(error),
            )
        except ToolInfrastructureError as error:
            stop_state = "invalidated"
            stop_reason = "infrastructure_failure"
            stop_detail = str(error)
            evidence.decision(
                "run_exception",
                classification="infrastructure_failure",
                detail=str(error),
            )
        except Exception as error:
            stop_state = "invalidated"
            stop_reason = "runner_error"
            stop_detail = f"{type(error).__name__}: {error}"
            evidence.decision(
                "run_exception",
                classification="runner_error",
                detail=stop_detail,
            )

        ended_at = self._timestamp()
        elapsed = max(0.0, self._monotonic() - started_monotonic)
        metadata["lifecycle_state"] = stop_state
        metadata["validity_status"] = "invalid" if stop_state == "invalidated" else "pending"
        metadata["timing"] = {
            "started_at": started_at,
            "ended_at": ended_at,
            "elapsed_seconds": elapsed,
        }
        metadata["stopping"] = {
            "reason": stop_reason,
            "detail": stop_detail,
            "submission_signal": (
                "api_submit_marker" if stop_reason == "submitted" else None
            ),
            "submit_marker_seen": stop_reason == "submitted",
        }
        usage.apply(metadata)
        self._atomic_metadata(metadata_path, metadata)
        evidence.finish_clarification_log(
            metadata["run_id"],
            metadata["task"]["task_id"],
            metadata["clarification"]["opportunity"],
            clarification_events,
            status="aborted" if stop_state == "invalidated" else "completed",
        )
        evidence.decision(
            "run_stopped",
            lifecycle_state=stop_state,
            stop_reason=stop_reason,
            actions_executed=actions,
            model_turns=turns,
            elapsed_seconds=elapsed,
        )
        return RunOutcome(stop_state, stop_reason, actions, turns, elapsed)

    def _preflight(
        self,
        metadata: dict[str, Any],
        evidence_directory: Path,
        workspace: Path,
    ) -> None:
        if metadata.get("lifecycle_state") != "prepared":
            raise WrapperConfigurationError("API wrapper requires a prepared run")
        if metadata.get("system", {}).get("evaluation_interface") != "api_wrapper":
            raise WrapperConfigurationError("Run is not configured for the API wrapper")
        if not workspace.is_dir():
            raise WrapperConfigurationError(f"Workspace does not exist: {workspace}")
        if not evidence_directory.is_dir():
            raise WrapperConfigurationError(
                f"Evidence directory does not exist: {evidence_directory}"
            )
        if not isinstance(getattr(self.transport, "provider_name", None), str):
            raise WrapperConfigurationError("Transport must expose provider_name")
        if getattr(self.transport, "contract_version", None) != TRANSPORT_CONTRACT_VERSION:
            raise WrapperConfigurationError(
                f"Transport must implement contract {TRANSPORT_CONTRACT_VERSION}"
            )
        if not self.system_prompt.strip():
            raise WrapperConfigurationError("System prompt must be non-empty")
        limits = metadata.get("limits", {})
        if not isinstance(limits.get("api_action_limit"), int):
            raise WrapperConfigurationError("API action limit is not configured")
        if not isinstance(limits.get("command_timeout_seconds"), int):
            raise WrapperConfigurationError("Command timeout is not configured")
        no_action_limit = limits.get("consecutive_no_action_response_limit")
        if not isinstance(no_action_limit, int) or isinstance(no_action_limit, bool) or no_action_limit < 1:
            raise WrapperConfigurationError(
                "Consecutive no-action response limit is not configured"
            )
        if metadata.get("phase") in {"pilot", "main"}:
            required = {
                "system.configuration_sha256": metadata["system"]["configuration_sha256"],
                "schedule.order_position": metadata["schedule"]["order_position"],
                "schedule.random_seed": metadata["schedule"]["random_seed"],
                "limits.task_wall_clock_seconds": limits["task_wall_clock_seconds"],
            }
            missing = [label for label, value in required.items() if value is None]
            if missing:
                raise WrapperConfigurationError(
                    "Pilot/main run is not frozen: " + ", ".join(missing)
                )

    def _validate_turn(self, turn: Any, seen_call_ids: set[str]) -> None:
        try:
            validate_model_turn(turn, require_attempts=True)
        except TransportContractError as error:
            raise WrapperInvariantError(str(error)) from error
        for call in turn.tool_calls:
            if not call.call_id or call.call_id in seen_call_ids:
                raise WrapperInvariantError(f"Duplicate or empty tool call ID: {call.call_id!r}")
            seen_call_ids.add(call.call_id)

    def _wall_clock_reached(
        self, metadata: dict[str, Any], started_monotonic: float
    ) -> bool:
        limit = metadata["limits"]["task_wall_clock_seconds"]
        return limit is not None and self._monotonic() - started_monotonic >= limit

    def _record_clarification_request(
        self,
        metadata: dict[str, Any],
        events: list[dict[str, Any]],
        call: ToolCall,
        sequence: int,
    ) -> None:
        request_text = call.arguments.get("request")
        if not isinstance(request_text, str):
            request_text = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
        metadata["clarification"]["requests"] += 1
        events.append(
            {
                "event_type": "request",
                "sequence": sequence,
                "call_id": call.call_id,
                "request_text": request_text,
                "timestamp": self._timestamp(),
            }
        )

    def _record_clarification_decision(
        self,
        metadata: dict[str, Any],
        events: list[dict[str, Any]],
        call: ToolCall,
        result: ToolExecutionResult,
    ) -> None:
        clarification = result.metadata.get("clarification", {})
        authorized = clarification.get("authorized") is True
        response_issued = clarification.get("response_issued") is True
        if authorized and not metadata["clarification"]["opportunity"]:
            raise WrapperInvariantError(
                "Complete-brief runs cannot authorize clarification requests"
            )
        if response_issued and not authorized:
            raise WrapperInvariantError(
                "Clarification response cannot be issued for an unauthorized request"
            )
        if authorized:
            metadata["clarification"]["authorized_requests"] += 1
        events.append(
            {
                "event_type": "decision",
                "call_id": call.call_id,
                "authorized": authorized,
                "reason_code": clarification.get("reason_code"),
                "timestamp": self._timestamp(),
            }
        )
        if response_issued:
            if metadata["clarification"]["responses"] >= 1:
                raise WrapperInvariantError(
                    "The frozen clarification protocol allows at most one response"
                )
            metadata["clarification"]["responses"] += 1
            events.append(
                {
                    "event_type": "response",
                    "call_id": call.call_id,
                    "response_card_id": clarification.get("response_card_id"),
                    "timestamp": self._timestamp(),
                }
            )

    def _timestamp(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            raise WrapperInvariantError("Clock returned a timezone-naive datetime")
        return value.isoformat()

    @staticmethod
    def _atomic_metadata(path: Path, metadata: dict[str, Any]) -> None:
        temporary = path.with_name(path.name + ".tmp")
        write_json(temporary, metadata)
        temporary.replace(path)


class _EvidenceWriter:
    def __init__(self, evidence_directory: Path, now: Callable[[], datetime]) -> None:
        self.directory = evidence_directory
        self._now = now
        self.raw_path = self.directory / ARTIFACT_PATHS["raw_model_response"]
        self.decision_path = self.directory / ARTIFACT_PATHS["adapter_decisions"]
        self.transcript_path = self.directory / ARTIFACT_PATHS["transcript"]
        self.clarification_path = self.directory / ARTIFACT_PATHS["clarification_log"]

    def start(self, task_prompt: str, provider: str) -> None:
        self.raw_path.write_text("", encoding="utf-8")
        self.decision_path.write_text("", encoding="utf-8")
        self.transcript_path.write_text(
            f"[TASK]\n{task_prompt.rstrip()}\n\n", encoding="utf-8"
        )
        write_json(
            self.clarification_path,
            {"schema_version": "1.0.0", "status": "running", "events": []},
        )
        self.raw_error("run_started", provider=provider)
        self.decision("evidence_started", provider=provider)

    def raw_response(self, turn_number: int, provider: str, turn: ModelTurn) -> None:
        self._append_jsonl(
            self.raw_path,
            {
                "record_type": "model_response",
                "timestamp": self._timestamp(),
                "turn": turn_number,
                "provider": provider,
                "response_id": turn.response_id,
                "finish_reason": turn.finish_reason,
                "transport_attempts": attempt_records_json(turn.transport_attempts),
                "raw_payload": turn.raw_payload,
                "usage": {
                    "input_tokens": turn.usage.input_tokens,
                    "output_tokens": turn.usage.output_tokens,
                    "cached_input_tokens": turn.usage.cached_input_tokens,
                    "reasoning_output_tokens": turn.usage.reasoning_output_tokens,
                    "provider_reported_total_tokens": (
                        turn.usage.provider_reported_total_tokens
                    ),
                    "monetary_cost": turn.usage.monetary_cost,
                    "currency": turn.usage.currency,
                }
                if turn.usage is not None
                else None,
                "normalized": {
                    "text": turn.text,
                    "tool_calls": [
                        {
                            "call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "argument_error": call.argument_error,
                        }
                        for call in turn.tool_calls
                    ],
                    "normalization_metadata": getattr(
                        turn, "normalization_metadata", {}
                    ),
                },
            },
        )

    def raw_error(self, record_type: str, **values: Any) -> None:
        self._append_jsonl(
            self.raw_path,
            {"record_type": record_type, "timestamp": self._timestamp(), **values},
        )

    def decision(self, decision_type: str, **values: Any) -> None:
        self._append_jsonl(
            self.decision_path,
            {"decision_type": decision_type, "timestamp": self._timestamp(), **values},
        )

    def assistant(self, text: str, calls: tuple[ToolCall, ...]) -> None:
        call_lines = "\n".join(
            f"[TOOL_CALL] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}"
            for call in calls
        )
        self._append_transcript(
            "ASSISTANT",
            "\n".join(part for part in (text, call_lines) if part),
        )

    def tool_result(self, call: ToolCall, result: ToolExecutionResult) -> None:
        self.decision(
            "tool_result",
            call_id=call.call_id,
            tool_name=call.name,
            is_error=result.is_error,
            metadata=result.metadata,
        )
        self._append_transcript(
            f"TOOL {call.name} {'ERROR' if result.is_error else 'OK'}",
            result.output,
        )

    def finish_clarification_log(
        self,
        run_id: str,
        task_id: str,
        opportunity: bool,
        events: list[dict[str, Any]],
        *,
        status: str,
    ) -> None:
        write_json(
            self.clarification_path,
            {
                "schema_version": "1.0.0",
                "status": status,
                "run_id": run_id,
                "task_id": task_id,
                "clarification_opportunity": opportunity,
                "events": events,
            },
        )

    def _append_transcript(self, label: str, content: str) -> None:
        with self.transcript_path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{self._timestamp()}] {label}\n{content}\n\n")

    @staticmethod
    def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")

    def _timestamp(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            raise WrapperInvariantError("Clock returned a timezone-naive datetime")
        return value.isoformat()
