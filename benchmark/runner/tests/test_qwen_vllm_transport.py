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
    OpenAIResponsesTransport,
)
from benchmark.runner.api_wrapper.transports.qwen_vllm import (
    QWEN_2_5_CODER_7B_MODEL,
    QwenVllmTransport,
    QwenWireResponse,
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
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1786200000,
        "model": QWEN_2_5_CODER_7B_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Done."},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens": 12,
            "completion_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 112,
        },
    }


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class QwenVllmTransportTests(unittest.TestCase):
    def _generate_compatibility_candidate(self, content: str, *, response_id: str = "chatcmpl-compat"):
        payload = completed_payload()
        payload["id"] = response_id
        payload["choices"][0]["message"]["content"] = content
        return QwenVllmTransport(
            lambda _payload, _timeout: payload,
            monotonic=SequenceClock(0, 0),
        ).generate(request())

    def test_mock_text_response_serializes_and_normalizes_without_credentials(self) -> None:
        calls: list[tuple[dict, float]] = []

        def requester(payload: dict, timeout: float) -> dict:
            calls.append((payload, timeout))
            return completed_payload()

        turn = QwenVllmTransport(
            requester, monotonic=SequenceClock(10, 10.25)
        ).generate(request())

        self.assertEqual(turn.text, "Done.")
        self.assertEqual(turn.response_id, "chatcmpl-123")
        self.assertEqual(turn.finish_reason, "completed")
        self.assertEqual(turn.usage.input_tokens, 100)
        self.assertEqual(turn.usage.output_tokens, 12)
        self.assertEqual(turn.usage.cached_input_tokens, 40)
        self.assertEqual(turn.usage.reasoning_output_tokens, 0)
        self.assertEqual(turn.usage.provider_reported_total_tokens, 112)
        self.assertEqual(turn.transport_attempts[0].elapsed_seconds, 0.25)

        payload, timeout = calls[0]
        self.assertEqual(timeout, 120.0)
        self.assertEqual(payload["model"], QWEN_2_5_CODER_7B_MODEL)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertTrue(payload["parallel_tool_calls"])
        self.assertFalse(payload["stream"])
        self.assertEqual(set(payload["tools"][0]), {"type", "function"})
        self.assertTrue(payload["tools"][0]["function"]["strict"])
        self.assertNotIn("endpoint_url", payload)
        self.assertNotIn("api_key", payload)

    def test_manual_history_and_ordered_tool_calls_use_chat_messages(self) -> None:
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
            "id": "chatcmpl-tools",
            "model": QWEN_2_5_CODER_7B_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "I will check.",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "execute_bash",
                                    "arguments": '{"command":"pytest -q"}',
                                },
                            },
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": "not-json",
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": None,
        }

        def requester(payload: dict, _timeout: float) -> dict:
            captured.append(payload)
            return mock

        turn = QwenVllmTransport(
            requester, monotonic=SequenceClock(0, 1)
        ).generate(request(messages))

        self.assertEqual(turn.text, "I will check.")
        self.assertEqual([call.call_id for call in turn.tool_calls], ["call_1", "call_2"])
        self.assertEqual(turn.tool_calls[0].arguments, {"command": "pytest -q"})
        self.assertEqual(turn.tool_calls[1].arguments, {})
        self.assertEqual(turn.tool_calls[1].argument_error, "arguments_invalid_json")
        self.assertEqual(turn.finish_reason, "tool_calls")
        assistant = captured[0]["messages"][2]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "call_prior")
        tool_result = captured[0]["messages"][3]
        self.assertEqual(tool_result["role"], "tool")
        self.assertEqual(tool_result["tool_call_id"], "call_prior")

    def test_exact_fenced_json_tool_call_is_normalized_without_semantic_repair(self) -> None:
        content = (
            "```json\n"
            '{"name": "read_file", "arguments": {"path": "SMOKE_TARGET.txt"}}'
            "\n```"
        )
        first = self._generate_compatibility_candidate(content)
        second = self._generate_compatibility_candidate(content)

        self.assertEqual(first.text, "")
        self.assertEqual(first.finish_reason, "tool_calls")
        self.assertEqual(len(first.tool_calls), 1)
        self.assertEqual(first.tool_calls[0].name, "read_file")
        self.assertEqual(first.tool_calls[0].arguments, {"path": "SMOKE_TARGET.txt"})
        self.assertEqual(first.tool_calls[0].call_id, second.tool_calls[0].call_id)
        audit = first.normalization_metadata["compatibility_normalizer"]
        self.assertTrue(audit["applied"])
        self.assertEqual(
            audit["reason"], "single_fenced_tool_json_with_preserved_prose"
        )
        self.assertTrue(audit["synthetic_call_id"])
        self.assertFalse(audit["semantic_repair_performed"])
        self.assertEqual(
            first.raw_payload["choices"][0]["message"]["content"], content
        )

    def test_compatibility_call_id_changes_with_provider_response_id(self) -> None:
        content = (
            "```json\n"
            '{"name":"read_file","arguments":{"path":"README.md"}}'
            "\n```"
        )
        first = self._generate_compatibility_candidate(content, response_id="one")
        second = self._generate_compatibility_candidate(content, response_id="two")
        self.assertNotEqual(first.tool_calls[0].call_id, second.tool_calls[0].call_id)

    def test_prose_surrounding_one_fenced_call_is_preserved_exactly(self) -> None:
        content = (
            "I will inspect the target first.\n\n"
            "```json\n"
            '{"name":"read_file","arguments":{"path":"public/index.html"}}'
            "\n```\n"
            "Then I can decide the smallest edit."
        )
        turn = self._generate_compatibility_candidate(content)
        self.assertEqual(
            turn.text,
            "I will inspect the target first.\n\n\nThen I can decide the smallest edit.",
        )
        self.assertEqual(len(turn.tool_calls), 1)
        self.assertEqual(turn.tool_calls[0].name, "read_file")
        audit = turn.normalization_metadata["compatibility_normalizer"]
        self.assertTrue(audit["applied"])
        self.assertIn("prefix_sha256", audit)
        self.assertIn("suffix_sha256", audit)
        self.assertFalse(audit["semantic_repair_performed"])

    def test_prose_surrounding_one_unfenced_call_is_preserved_exactly(self) -> None:
        content = (
            "I will list the candidate files.\n\n"
            '{"name": "execute_bash", "arguments": {"command": "ls public/*.html"}}'
        )
        turn = self._generate_compatibility_candidate(content)
        self.assertEqual(turn.text, "I will list the candidate files.\n\n")
        self.assertEqual(len(turn.tool_calls), 1)
        self.assertEqual(turn.tool_calls[0].name, "execute_bash")
        self.assertEqual(
            turn.tool_calls[0].arguments, {"command": "ls public/*.html"}
        )
        audit = turn.normalization_metadata["compatibility_normalizer"]
        self.assertTrue(audit["applied"])
        self.assertEqual(
            audit["reason"], "single_unfenced_tool_json_with_preserved_prose"
        )
        self.assertEqual(audit["source_representation"], "unfenced")
        self.assertFalse(audit["semantic_repair_performed"])
        self.assertEqual(
            turn.raw_payload["choices"][0]["message"]["content"], content
        )

    def test_normalizer_rejects_ambiguous_or_schema_invalid_content(self) -> None:
        rejected = (
            (
                "No structured call here.",
                "eligible_unfenced_json_object_count_not_one",
            ),
            (
                "```json\n"
                '{"name":"read_file","arguments":{"path":"README.md"}}'
                "\n```\n```text\nextra\n```",
                "additional_fence_present",
            ),
            (
                "Context {ambiguous}.\n```json\n"
                '{"name":"read_file","arguments":{"path":"README.md"}}'
                "\n```",
                "additional_object_like_content_present",
            ),
            (
                "```json\n"
                '{"name":"read_file","arguments":{"path":"README.md"},"extra":true}'
                "\n```",
                "tool_object_keys_mismatch",
            ),
            (
                "```json\n"
                '{"name":"unknown","arguments":{"path":"README.md"}}'
                "\n```",
                "tool_name_not_frozen",
            ),
            (
                "```json\n"
                '{"name":"read_file","arguments":{"path":"README.md","other":"x"}}'
                "\n```",
                "arguments_schema_mismatch:property_set",
            ),
            (
                "```json\n"
                '{"name":"read_file","arguments":{"path":7}}'
                "\n```",
                "arguments_schema_mismatch:path_type",
            ),
            (
                "```json\n"
                '{"name":"read_file","arguments":{"path":""}}'
                "\n```",
                "arguments_schema_mismatch:path_minLength",
            ),
            (
                "First "
                '{"name":"read_file","arguments":{"path":"README.md"}} '
                "then "
                '{"name":"read_file","arguments":{"path":"index.html"}}',
                "eligible_unfenced_json_object_count_not_one",
            ),
            (
                "Context {ambiguous} before "
                '{"name":"read_file","arguments":{"path":"README.md"}}',
                "eligible_unfenced_json_object_count_not_one",
            ),
            (
                "Context with unmatched { before "
                '{"name":"read_file","arguments":{"path":"README.md"}}',
                "unmatched_unfenced_object_brace",
            ),
            (
                "I will inspect.\n"
                '{\n"name":"read_file","arguments":{"path":"README.md"}\n}',
                "unfenced_body_not_single_line",
            ),
            (
                "I will inspect. "
                '{"name":"read_file","arguments":{"path":"README.md"}} '
                "<SUBMIT_FIX>",
                "submit_marker_present",
            ),
        )
        for content, reason in rejected:
            with self.subTest(reason=reason):
                turn = self._generate_compatibility_candidate(content)
                self.assertEqual(turn.tool_calls, ())
                self.assertEqual(turn.text, content)
                self.assertFalse(
                    turn.normalization_metadata["compatibility_normalizer"]["applied"]
                )
                self.assertEqual(
                    turn.normalization_metadata["compatibility_normalizer"]["reason"],
                    reason,
                )

    def test_native_tool_call_bypasses_compatibility_normalizer(self) -> None:
        payload = completed_payload()
        payload["choices"][0]["message"] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "native-call",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"README.md"}',
                    },
                }
            ],
        }
        payload["choices"][0]["finish_reason"] = "tool_calls"
        turn = QwenVllmTransport(
            lambda _payload, _timeout: payload,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        self.assertEqual(turn.tool_calls[0].call_id, "native-call")
        self.assertFalse(
            turn.normalization_metadata["compatibility_normalizer"]["applied"]
        )
        self.assertEqual(
            turn.normalization_metadata["compatibility_normalizer"]["reason"],
            "native_tool_calls_present",
        )

    def test_finish_reasons_and_malformed_choices_follow_common_contract(self) -> None:
        length = completed_payload()
        length["choices"][0]["message"]["content"] = "Partial"
        length["choices"][0]["finish_reason"] = "length"
        turn = QwenVllmTransport(
            lambda _payload, _timeout: length,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        self.assertEqual(turn.finish_reason, "max_output_tokens")

        refusal = completed_payload()
        refusal["choices"][0]["message"] = {
            "role": "assistant",
            "content": None,
            "refusal": "Cannot comply.",
        }
        turn = QwenVllmTransport(
            lambda _payload, _timeout: refusal,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        self.assertEqual(turn.text, "Cannot comply.")
        self.assertEqual(turn.finish_reason, "refusal")

        malformed = completed_payload()
        malformed["choices"].append(malformed["choices"][0])
        with self.assertRaises(TransportContractError):
            QwenVllmTransport(
                lambda _payload, _timeout: malformed,
                monotonic=SequenceClock(0, 0),
            ).generate(request())

    def test_retry_audit_and_terminal_error_match_frozen_policy(self) -> None:
        responses = iter(
            [
                QwenWireResponse(
                    {"error": {"type": "server_error", "code": "overloaded"}},
                    http_status=503,
                    headers={"Retry-After": "2", "x-request-id": "hf_failed"},
                ),
                QwenWireResponse(
                    completed_payload(), headers={"x-request-id": "hf_success"}
                ),
            ]
        )
        payloads: list[dict] = []
        sleeps: list[float] = []

        def requester(payload: dict, _timeout: float) -> QwenWireResponse:
            payloads.append(payload)
            return next(responses)

        turn = QwenVllmTransport(
            requester,
            monotonic=SequenceClock(0, 0.5, 2.5, 3.0),
            sleep=sleeps.append,
        ).generate(request())
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(
            [attempt.outcome for attempt in turn.transport_attempts],
            ["retryable_error", "success"],
        )

        terminal = QwenWireResponse(
            {"error": {"type": "invalid_request_error", "code": "bad_model"}},
            http_status=404,
            headers={"x-request-id": "hf_model"},
        )
        with self.assertRaises(TransportInfrastructureError) as caught:
            QwenVllmTransport(
                lambda _payload, _timeout: terminal,
                monotonic=SequenceClock(0, 0.1),
            ).generate(request())
        self.assertEqual(caught.exception.attempts, 1)
        self.assertEqual(caught.exception.attempt_records[0].http_status, 404)
        self.assertEqual(caught.exception.attempt_records[0].outcome, "terminal_error")

    def test_provider_specific_mocks_normalize_to_symmetric_common_fields(self) -> None:
        openai_payload = {
            "id": "resp-openai",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Done."}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 12,
                "total_tokens": 112,
            },
        }
        qwen_payload = completed_payload()
        openai_turn = OpenAIResponsesTransport(
            lambda _payload, _timeout: openai_payload,
            monotonic=SequenceClock(0, 0),
        ).generate(request())
        qwen_turn = QwenVllmTransport(
            lambda _payload, _timeout: qwen_payload,
            monotonic=SequenceClock(0, 0),
        ).generate(request())

        self.assertEqual(openai_turn.text, qwen_turn.text)
        self.assertEqual(openai_turn.tool_calls, qwen_turn.tool_calls)
        self.assertEqual(openai_turn.finish_reason, qwen_turn.finish_reason)
        self.assertEqual(openai_turn.usage.input_tokens, qwen_turn.usage.input_tokens)
        self.assertEqual(openai_turn.usage.output_tokens, qwen_turn.usage.output_tokens)
        self.assertEqual(
            openai_turn.usage.provider_reported_total_tokens,
            qwen_turn.usage.provider_reported_total_tokens,
        )


if __name__ == "__main__":
    unittest.main()
