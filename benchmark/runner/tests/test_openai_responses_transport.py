from __future__ import annotations

import unittest

from benchmark.runner.api_wrapper.contracts import (
    TOOL_DEFINITIONS,
    ContextMessage,
    ToolCall,
    TransportContractError,
    TransportInfrastructureError,
    TransportPolicy,
    TransportRequest,
)
from benchmark.runner.api_wrapper.transports.openai_responses import (
    OPENAI_GPT_5_4_MODEL,
    OpenAIResponsesTransport,
    OpenAIWireResponse,
)


def request(messages: tuple[ContextMessage, ...] | None = None) -> TransportRequest:
    return TransportRequest(
        logical_request_id="run-1:turn:1",
        model_turn=1,
        messages=messages
        or (
            ContextMessage("system", "Use the logical tools."),
            ContextMessage("user", "Fix the task."),
        ),
        tool_definitions=TOOL_DEFINITIONS,
        policy=TransportPolicy(),
    )


def completed_payload() -> dict:
    return {
        "id": "resp_123",
        "object": "response",
        "status": "completed",
        "output": [
            {
                "id": "msg_123",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Done.", "annotations": []}
                ],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens": 12,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 112,
        },
    }


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class OpenAIResponsesTransportTests(unittest.TestCase):
    def test_mock_text_response_serializes_and_normalizes_without_credentials(self) -> None:
        calls: list[tuple[dict, float]] = []

        def requester(payload: dict, timeout: float) -> dict:
            calls.append((payload, timeout))
            return completed_payload()

        transport = OpenAIResponsesTransport(
            requester, monotonic=SequenceClock(10.0, 10.25)
        )
        turn = transport.generate(request())

        self.assertEqual(turn.text, "Done.")
        self.assertEqual(turn.response_id, "resp_123")
        self.assertEqual(turn.finish_reason, "completed")
        self.assertEqual(turn.usage.input_tokens, 100)
        self.assertEqual(turn.usage.cached_input_tokens, 40)
        self.assertEqual(turn.usage.reasoning_output_tokens, 2)
        self.assertEqual(turn.usage.provider_reported_total_tokens, 112)
        self.assertEqual(turn.transport_attempts[0].provider_request_id, "resp_123")
        self.assertEqual(turn.transport_attempts[0].elapsed_seconds, 0.25)

        payload, timeout = calls[0]
        self.assertEqual(timeout, 120.0)
        self.assertEqual(payload["model"], OPENAI_GPT_5_4_MODEL)
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertEqual(payload["input"][1]["role"], "user")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        self.assertEqual(payload["max_output_tokens"], 4096)
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertTrue(payload["parallel_tool_calls"])
        self.assertFalse(payload["stream"])
        self.assertNotIn("previous_response_id", payload)
        self.assertEqual(
            set(payload["tools"][0]),
            {"type", "name", "description", "parameters", "strict"},
        )
        self.assertTrue(all(tool["strict"] for tool in payload["tools"]))

    def test_manual_history_and_ordered_tool_calls_use_responses_items(self) -> None:
        prior_call = ToolCall("call_prior", "read_file", {"path": "README.md"})
        messages = (
            ContextMessage("system", "system"),
            ContextMessage("user", "task"),
            ContextMessage("assistant", "Checking.", tool_calls=(prior_call,)),
            ContextMessage(
                "tool",
                "contents",
                tool_call_id="call_prior",
                tool_name="read_file",
            ),
        )
        captured: list[dict] = []
        mock = {
            "id": "resp_tools",
            "status": "completed",
            "output": [
                {"id": "rs_1", "type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "I will "}],
                },
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "execute_bash",
                    "arguments": '{"command":"pytest -q"}',
                    "status": "completed",
                },
                {
                    "type": "function_call",
                    "id": "fc_2",
                    "call_id": "call_2",
                    "name": "read_file",
                    "arguments": "not-json",
                    "status": "completed",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "check."}],
                },
            ],
            "usage": None,
        }

        def requester(payload: dict, _timeout: float) -> dict:
            captured.append(payload)
            return mock

        turn = OpenAIResponsesTransport(
            requester, monotonic=SequenceClock(0, 1)
        ).generate(request(messages))

        self.assertEqual(turn.text, "I will check.")
        self.assertEqual([call.call_id for call in turn.tool_calls], ["call_1", "call_2"])
        self.assertEqual(turn.tool_calls[0].arguments, {"command": "pytest -q"})
        self.assertEqual(turn.tool_calls[1].arguments, {})
        self.assertEqual(turn.tool_calls[1].argument_error, "arguments_invalid_json")
        self.assertEqual(turn.finish_reason, "tool_calls")
        self.assertIsNone(turn.usage)
        self.assertEqual(
            captured[0]["input"][2],
            {"role": "assistant", "content": "Checking."},
        )
        self.assertEqual(captured[0]["input"][3]["type"], "function_call")
        self.assertEqual(captured[0]["input"][4]["type"], "function_call_output")
        self.assertEqual(captured[0]["input"][4]["call_id"], "call_prior")

    def test_refusal_and_incomplete_statuses_map_to_frozen_finish_reasons(self) -> None:
        refusal = {
            "id": "resp_refusal",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "Cannot comply."}],
                }
            ],
        }
        turn = OpenAIResponsesTransport(
            lambda _payload, _timeout: refusal,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        self.assertEqual(turn.text, "Cannot comply.")
        self.assertEqual(turn.finish_reason, "refusal")

        incomplete = {
            "id": "resp_incomplete",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Partial"}],
                }
            ],
        }
        turn = OpenAIResponsesTransport(
            lambda _payload, _timeout: incomplete,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        self.assertEqual(turn.finish_reason, "max_output_tokens")

    def test_retry_audit_honors_retry_after_and_reuses_same_payload(self) -> None:
        responses = iter(
            [
                OpenAIWireResponse(
                    {"error": {"type": "rate_limit_error", "code": "rate_limit"}},
                    http_status=429,
                    headers={"Retry-After": "5", "x-request-id": "req_failed"},
                ),
                OpenAIWireResponse(
                    completed_payload(), headers={"x-request-id": "req_success"}
                ),
            ]
        )
        payloads: list[dict] = []
        sleeps: list[float] = []

        def requester(payload: dict, _timeout: float) -> OpenAIWireResponse:
            payloads.append(payload)
            return next(responses)

        turn = OpenAIResponsesTransport(
            requester,
            monotonic=SequenceClock(0, 0.5, 5.5, 6.25),
            sleep=sleeps.append,
        ).generate(request())

        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(sleeps, [5.0])
        self.assertEqual(
            [attempt.outcome for attempt in turn.transport_attempts],
            ["retryable_error", "success"],
        )
        self.assertEqual(turn.transport_attempts[0].http_status, 429)
        self.assertEqual(turn.transport_attempts[0].provider_request_id, "req_failed")
        self.assertEqual(turn.transport_attempts[1].provider_request_id, "req_success")

    def test_terminal_error_and_malformed_success_are_distinct(self) -> None:
        terminal = OpenAIWireResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
            http_status=401,
            headers={"x-request-id": "req_auth"},
        )
        transport = OpenAIResponsesTransport(
            lambda _payload, _timeout: terminal,
            monotonic=SequenceClock(0, 0.1),
        )
        with self.assertRaises(TransportInfrastructureError) as caught:
            transport.generate(request())
        self.assertEqual(caught.exception.attempts, 1)
        self.assertEqual(caught.exception.attempt_records[-1].outcome, "terminal_error")
        self.assertEqual(caught.exception.attempt_records[-1].http_status, 401)

        malformed = {"id": "resp_bad", "status": "completed", "output": "bad"}
        transport = OpenAIResponsesTransport(
            lambda _payload, _timeout: malformed,
            monotonic=SequenceClock(0, 0.1),
        )
        with self.assertRaises(TransportContractError):
            transport.generate(request())


if __name__ == "__main__":
    unittest.main()
