"""Unit tests for phoenix_core.memory.context_builder.ContextBuilder."""
import pytest

from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.models import Conversation, Message


def make_conversation(*messages: Message) -> Conversation:
    return Conversation(conversation_id="c1", user_id=1, messages=list(messages))


class TestBuild:
    def test_empty_conversation_returns_empty_list(self) -> None:
        builder = ContextBuilder()
        assert builder.build(make_conversation()) == []

    def test_returns_provider_shaped_messages_in_order(self) -> None:
        builder = ContextBuilder()
        conversation = make_conversation(
            Message(role="user", content="hi"),
            Message(role="assistant", content="hello"),
        )

        result = builder.build(conversation)

        assert result == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

    def test_does_not_mutate_the_conversation(self) -> None:
        builder = ContextBuilder(max_context_chars=1)
        conversation = make_conversation(
            Message(role="user", content="a very long message here"),
            Message(role="assistant", content="another one"),
        )

        builder.build(conversation)

        assert len(conversation.messages) == 2  # untouched


class TestCharBudget:
    def test_drops_oldest_messages_once_over_budget(self) -> None:
        builder = ContextBuilder(max_context_chars=12)
        conversation = make_conversation(
            Message(role="user", content="0123456789"),   # 10 chars, oldest -> dropped
            Message(role="assistant", content="01234"),   # 5 chars
            Message(role="user", content="0123456"),      # 7 chars -> 5+7=12, fits
        )

        result = builder.build(conversation)

        assert result == [
            {"role": "assistant", "content": "01234"},
            {"role": "user", "content": "0123456"},
        ]

    def test_always_keeps_the_single_most_recent_message_even_if_oversized(self) -> None:
        builder = ContextBuilder(max_context_chars=3)
        conversation = make_conversation(
            Message(role="user", content="short"),
            Message(role="assistant", content="this is way over budget"),
        )

        result = builder.build(conversation)

        assert result == [{"role": "assistant", "content": "this is way over budget"}]

    def test_invalid_max_context_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            ContextBuilder(max_context_chars=0)
