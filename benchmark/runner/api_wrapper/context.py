from __future__ import annotations

from dataclasses import dataclass

from .contracts import ContextMessage, ModelTurn, ToolExecutionResult


@dataclass(frozen=True)
class ContextSnapshot:
    messages: tuple[ContextMessage, ...]
    character_count: int
    retained_turns: int
    dropped_turns: int


class ConversationContext:
    """Keeps immutable prompt messages and complete assistant/tool turn groups."""

    def __init__(
        self,
        system_prompt: str,
        task_prompt: str,
        *,
        max_characters: int | None = None,
    ) -> None:
        if not system_prompt.strip() or not task_prompt.strip():
            raise ValueError("System and task prompts must be non-empty")
        if max_characters is not None and max_characters < 1:
            raise ValueError("max_characters must be positive or null")
        self._prefix = (
            ContextMessage("system", system_prompt),
            ContextMessage("user", task_prompt),
        )
        self._turns: list[list[ContextMessage]] = []
        self._dropped_turns = 0
        self._max_characters = max_characters

    def append_model_turn(self, turn: ModelTurn) -> None:
        self._turns.append(
            [
                ContextMessage(
                    "assistant",
                    turn.text,
                    tool_calls=turn.tool_calls,
                )
            ]
        )
        self._prune()

    def append_tool_result(
        self,
        call_id: str,
        tool_name: str,
        result: ToolExecutionResult,
    ) -> None:
        if not self._turns:
            raise RuntimeError("Tool results require a preceding assistant turn")
        self._turns[-1].append(
            ContextMessage(
                "tool",
                result.output,
                tool_call_id=call_id,
                tool_name=tool_name,
            )
        )
        self._prune()

    def snapshot(self) -> ContextSnapshot:
        messages: list[ContextMessage] = [self._prefix[0]]
        if self._dropped_turns:
            messages.append(
                ContextMessage(
                    "system",
                    f"[CONTEXT_NOTICE] {self._dropped_turns} older complete model turn(s) "
                    "were removed by the frozen context limit.",
                )
            )
        messages.append(self._prefix[1])
        for turn in self._turns:
            messages.extend(turn)
        return ContextSnapshot(
            messages=tuple(messages),
            character_count=sum(len(message.content) for message in messages),
            retained_turns=len(self._turns),
            dropped_turns=self._dropped_turns,
        )

    def _prune(self) -> None:
        if self._max_characters is None:
            return
        while len(self._turns) > 1 and self._raw_character_count() > self._max_characters:
            self._turns.pop(0)
            self._dropped_turns += 1

    def _raw_character_count(self) -> int:
        return sum(len(message.content) for message in self._prefix) + sum(
            len(message.content) for turn in self._turns for message in turn
        )
