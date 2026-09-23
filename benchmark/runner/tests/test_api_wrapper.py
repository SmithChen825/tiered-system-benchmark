from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmark.runner.api_wrapper.context import ConversationContext
from benchmark.runner.api_wrapper.contracts import (
    ModelTurn,
    TRANSPORT_CONTRACT_VERSION,
    ToolCall,
    ToolCommandTimeout,
    ToolExecutionResult,
    TransportInfrastructureError,
    TransportAttempt,
    UsageDelta,
)
from benchmark.runner.api_wrapper.core import ApiAgentRunner, WrapperSettings
from benchmark.runner.common import REPOSITORY_ROOT, load_json, write_json
from benchmark.runner.create_run import create_run
from benchmark.runner.evidence_validator import validate_run


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.origin = datetime(2026, 8, 8, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.value

    def now(self) -> datetime:
        return self.origin + timedelta(seconds=self.value)

    def advance(self, seconds: float) -> None:
        self.value += seconds


class QueueTransport:
    provider_name = "mock-provider"
    contract_version = TRANSPORT_CONTRACT_VERSION

    def __init__(self, responses, *, clock: FakeClock | None = None, advance: float = 0):
        self.responses = list(responses)
        self.messages_seen = []
        self.clock = clock
        self.advance = advance

    def generate(self, request):
        self.messages_seen.append(request.messages)
        self.tool_definitions = request.tool_definitions
        self.requests_seen = getattr(self, "requests_seen", []) + [request]
        if self.clock and self.advance:
            self.clock.advance(self.advance)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, ModelTurn) and not value.transport_attempts:
            value = replace(
                value,
                transport_attempts=(TransportAttempt(1, "success", self.advance),),
            )
        return value


class RecordingExecutor:
    def __init__(self, results=None, error: Exception | None = None):
        self.calls = []
        self.results = results or {}
        self.error = error

    def execute(self, call, *, workspace, command_timeout_seconds):
        self.calls.append((call, workspace, command_timeout_seconds))
        if self.error:
            raise self.error
        return self.results.get(
            call.call_id,
            ToolExecutionResult(f"result:{call.name}:{call.call_id}"),
        )


class ApiWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = REPOSITORY_ROOT / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="api-wrapper-", dir=parent)
        self.root = Path(self.temporary.name)
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self, task_id: str = "L1-01") -> tuple[Path, Path]:
        return create_run(
            task_id=task_id,
            system_id="gpt-5.4",
            phase="validation",
            repetition=1,
            attempt=1,
            runs_root=self.root / "runs",
            workspaces_root=self.root / "workspaces",
        )

    def runner(self, transport, executor, *, max_context=None) -> ApiAgentRunner:
        return ApiAgentRunner(
            transport=transport,
            tool_executor=executor,
            system_prompt="You are the frozen mock API agent.",
            settings=WrapperSettings(max_context_characters=max_context),
            now=self.clock.now,
            monotonic=self.clock.monotonic,
        )

    def assert_valid(self, evidence: Path, workspace: Path) -> None:
        self.assertEqual(validate_run(evidence, workspace=workspace), [])

    def test_exact_submit_marker_submits_without_counting_or_executing_tools(self) -> None:
        evidence, workspace = self.prepare()
        call = ToolCall("ignored", "read_file", {"path": "README.md"})
        transport = QueueTransport(
            [
                ModelTurn(
                    text="Repair complete. <SUBMIT_FIX>",
                    tool_calls=(call,),
                    raw_payload={"id": "response-1"},
                    usage=UsageDelta(10, 4),
                )
            ]
        )
        executor = RecordingExecutor()
        outcome = self.runner(transport, executor).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "submitted")
        self.assertEqual(outcome.actions_executed, 0)
        self.assertEqual(executor.calls, [])
        metadata = load_json(evidence / "metadata.json")
        self.assertTrue(metadata["stopping"]["submit_marker_seen"])
        self.assertEqual(
            metadata["stopping"]["submission_signal"], "api_submit_marker"
        )
        self.assertEqual(metadata["usage"]["total_tokens"], 14)
        self.assert_valid(evidence, workspace)

    def test_multiple_calls_are_counted_and_results_return_to_context(self) -> None:
        evidence, workspace = self.prepare()
        calls = (
            ToolCall("read-1", "read_file", {"path": "README.md"}),
            ToolCall("patch-1", "patch_file", {"patch": "test patch"}),
        )
        transport = QueueTransport(
            [
                ModelTurn(text="Inspecting.", tool_calls=calls, raw_payload={"turn": 1}),
                ModelTurn(text="<SUBMIT_FIX>", raw_payload={"turn": 2}),
            ]
        )
        executor = RecordingExecutor()
        outcome = self.runner(transport, executor).run(evidence, workspace)
        self.assertEqual(outcome.actions_executed, 2)
        self.assertEqual(len(executor.calls), 2)
        second_context = transport.messages_seen[1]
        self.assertEqual([item.role for item in second_context[-3:]], ["assistant", "tool", "tool"])
        self.assert_valid(evidence, workspace)

    def test_three_consecutive_no_action_responses_suspend_validly(self) -> None:
        evidence, workspace = self.prepare()
        transport = QueueTransport(
            [
                ModelTurn(text="Thinking one.", raw_payload={"turn": 1}),
                ModelTurn(text="Thinking two.", raw_payload={"turn": 2}),
                ModelTurn(text="Thinking three.", raw_payload={"turn": 3}),
            ]
        )
        outcome = self.runner(transport, RecordingExecutor()).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "suspended")
        self.assertEqual(outcome.stop_reason, "protocol_no_progress_limit")
        self.assertEqual(outcome.model_turns, 3)
        self.assertEqual(outcome.actions_executed, 0)
        self.assert_valid(evidence, workspace)

    def test_accepted_action_resets_no_action_streak(self) -> None:
        evidence, workspace = self.prepare()
        transport = QueueTransport(
            [
                ModelTurn(text="Thinking one.", raw_payload={"turn": 1}),
                ModelTurn(text="Thinking two.", raw_payload={"turn": 2}),
                ModelTurn(
                    tool_calls=(ToolCall("read", "read_file", {"path": "README.md"}),),
                    raw_payload={"turn": 3},
                ),
                ModelTurn(text="Thinking again.", raw_payload={"turn": 4}),
                ModelTurn(text="<SUBMIT_FIX>", raw_payload={"turn": 5}),
            ]
        )
        outcome = self.runner(transport, RecordingExecutor()).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "submitted")
        self.assertEqual(outcome.actions_executed, 1)
        self.assert_valid(evidence, workspace)

    def test_action_limit_blocks_calls_beyond_frozen_count(self) -> None:
        evidence, workspace = self.prepare()
        metadata = load_json(evidence / "metadata.json")
        metadata["limits"]["api_action_limit"] = 2
        write_json(evidence / "metadata.json", metadata)
        calls = tuple(
            ToolCall(f"read-{index}", "read_file", {"path": "README.md"})
            for index in range(3)
        )
        executor = RecordingExecutor()
        outcome = self.runner(
            QueueTransport([ModelTurn(tool_calls=calls, raw_payload={"turn": 1})]),
            executor,
        ).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "suspended")
        self.assertEqual(outcome.stop_reason, "api_action_limit")
        self.assertEqual(outcome.actions_executed, 2)
        self.assertEqual(len(executor.calls), 2)
        self.assert_valid(evidence, workspace)

    def test_command_timeout_is_a_valid_suspension(self) -> None:
        evidence, workspace = self.prepare()
        call = ToolCall("bash-1", "execute_bash", {"command": "slow command"})
        executor = RecordingExecutor(error=ToolCommandTimeout("180 second timeout"))
        outcome = self.runner(
            QueueTransport([ModelTurn(tool_calls=(call,), raw_payload={"turn": 1})]),
            executor,
        ).run(evidence, workspace)
        self.assertEqual(outcome.stop_reason, "command_timeout")
        self.assertEqual(outcome.actions_executed, 1)
        self.assert_valid(evidence, workspace)

    def test_wall_clock_limit_has_priority_over_late_submission(self) -> None:
        evidence, workspace = self.prepare()
        metadata = load_json(evidence / "metadata.json")
        metadata["limits"]["task_wall_clock_seconds"] = 10
        write_json(evidence / "metadata.json", metadata)
        transport = QueueTransport(
            [ModelTurn(text="<SUBMIT_FIX>", raw_payload={"turn": 1})],
            clock=self.clock,
            advance=11,
        )
        outcome = self.runner(transport, RecordingExecutor()).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "suspended")
        self.assertEqual(outcome.stop_reason, "task_wall_clock_limit")
        self.assertFalse(load_json(evidence / "metadata.json")["stopping"]["submit_marker_seen"])
        self.assertIsNone(
            load_json(evidence / "metadata.json")["stopping"]["submission_signal"]
        )
        self.assert_valid(evidence, workspace)

    def test_transport_failure_invalidates_and_retains_evidence(self) -> None:
        evidence, workspace = self.prepare()
        attempts = (
            TransportAttempt(
                1,
                "retryable_error",
                0.2,
                error_kind="server_error",
                http_status=503,
                retry_delay_seconds=1,
            ),
            TransportAttempt(
                2,
                "retryable_error",
                0.2,
                error_kind="server_error",
                http_status=503,
                retry_delay_seconds=2,
            ),
            TransportAttempt(
                3,
                "terminal_error",
                0.2,
                error_kind="server_error",
                http_status=503,
            ),
        )
        transport = QueueTransport(
            [
                TransportInfrastructureError(
                    "provider unavailable",
                    attempts=3,
                    attempt_records=attempts,
                )
            ]
        )
        outcome = self.runner(transport, RecordingExecutor()).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "invalidated")
        self.assertEqual(outcome.stop_reason, "infrastructure_failure")
        raw = (evidence / "raw_model_response.jsonl").read_text(encoding="utf-8")
        self.assertIn("transport_failure", raw)
        self.assertIn('"http_status":503', raw)
        self.assert_valid(evidence, workspace)

    def test_unexpected_executor_failure_is_runner_error(self) -> None:
        evidence, workspace = self.prepare()
        call = ToolCall("read-1", "read_file", {"path": "README.md"})
        executor = RecordingExecutor(error=RuntimeError("executor bug"))
        outcome = self.runner(
            QueueTransport([ModelTurn(tool_calls=(call,), raw_payload={"turn": 1})]),
            executor,
        ).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "invalidated")
        self.assertEqual(outcome.stop_reason, "runner_error")
        self.assertEqual(outcome.actions_executed, 1)
        self.assert_valid(evidence, workspace)

    def test_unknown_tool_is_rejected_without_counting_and_loop_continues(self) -> None:
        evidence, workspace = self.prepare()
        unknown = ToolCall("unknown-1", "delete_everything", {"path": "."})
        transport = QueueTransport(
            [
                ModelTurn(tool_calls=(unknown,), raw_payload={"turn": 1}),
                ModelTurn(text="<SUBMIT_FIX>", raw_payload={"turn": 2}),
            ]
        )
        executor = RecordingExecutor()
        outcome = self.runner(transport, executor).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "submitted")
        self.assertEqual(outcome.actions_executed, 0)
        self.assertEqual(executor.calls, [])
        self.assertIn("Unsupported logical tool", transport.messages_seen[1][-1].content)
        self.assert_valid(evidence, workspace)

    def test_clarification_events_and_counts_are_synchronized(self) -> None:
        evidence, workspace = self.prepare("L2-02")
        call = ToolCall(
            "clarify-1",
            "request_human_clarification",
            {"request": "May a task be created without a due date?"},
        )
        result = ToolExecutionResult(
            "Business rule: due_date is optional.",
            metadata={
                "clarification": {
                    "authorized": True,
                    "response_issued": True,
                    "response_card_id": "L2-02-R1",
                    "reason_code": "QUALIFYING_DUE_DATE_RULE",
                }
            },
        )
        transport = QueueTransport(
            [
                ModelTurn(tool_calls=(call,), raw_payload={"turn": 1}),
                ModelTurn(text="<SUBMIT_FIX>", raw_payload={"turn": 2}),
            ]
        )
        outcome = self.runner(
            transport, RecordingExecutor(results={"clarify-1": result})
        ).run(evidence, workspace)
        self.assertEqual(outcome.lifecycle_state, "submitted")
        metadata = load_json(evidence / "metadata.json")
        self.assertEqual(
            metadata["clarification"],
            {"opportunity": True, "requests": 1, "authorized_requests": 1, "responses": 1},
        )
        clarification = load_json(evidence / "clarification_log.json")
        self.assertEqual(
            [event["event_type"] for event in clarification["events"]],
            ["request", "decision", "response"],
        )
        self.assert_valid(evidence, workspace)

    def test_context_prunes_only_complete_old_turns(self) -> None:
        context = ConversationContext("system", "task", max_characters=20)
        first = ModelTurn(
            text="first-long-turn",
            tool_calls=(ToolCall("one", "read_file", {"path": "a"}),),
        )
        context.append_model_turn(first)
        context.append_tool_result("one", "read_file", ToolExecutionResult("first-result"))
        context.append_model_turn(ModelTurn(text="second-long-turn"))
        snapshot = context.snapshot()
        self.assertEqual(snapshot.dropped_turns, 1)
        self.assertEqual(snapshot.retained_turns, 1)
        self.assertNotIn("first-result", [message.content for message in snapshot.messages])
        self.assertIn("second-long-turn", [message.content for message in snapshot.messages])


if __name__ == "__main__":
    unittest.main()
