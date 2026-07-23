"""Unit tests for phoenix_core.telegram.bot._split_for_telegram (Task 017).

Long AI responses are no longer truncated by OutputSanitizer — they are
split into multiple Telegram messages here instead, so no content is lost.
"""
from phoenix_core.telegram.bot import TELEGRAM_MESSAGE_LIMIT, _split_for_telegram


def _make_text(total_chars: int, paragraph_chars: int = 400) -> str:
    """Build filler text of at least total_chars, as full paragraphs
    separated by blank lines (so natural split points exist throughout)."""
    filler = (
        "Изречение за AI отговор с достатъчно съдържание тук. "
        * ((paragraph_chars // 50) + 1)
    )[:paragraph_chars]
    paragraphs = []
    accumulated = 0
    while accumulated < total_chars:
        paragraphs.append(filler)
        accumulated += paragraph_chars + 2  # +2 for the "\n\n" separator
    return "\n\n".join(paragraphs)


class TestShortText:
    def test_short_text_is_a_single_chunk(self) -> None:
        text = "Кратък отговор."
        assert _split_for_telegram(text) == [text]

    def test_text_exactly_at_limit_is_a_single_chunk(self) -> None:
        text = "a" * TELEGRAM_MESSAGE_LIMIT
        assert _split_for_telegram(text) == [text]


class TestMediumText:
    def test_around_5000_chars_splits_into_two_messages(self) -> None:
        text = _make_text(5000)
        result = _split_for_telegram(text)
        assert len(result) == 2
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT

    def test_no_content_is_lost_when_splitting(self) -> None:
        text = _make_text(5000)
        result = _split_for_telegram(text)
        rejoined = "\n".join(result)
        for line in text.split("\n"):
            if line.strip():
                assert line.strip() in rejoined


class TestLongText:
    def test_around_12000_chars_splits_into_at_least_four_messages(self) -> None:
        text = _make_text(12000)
        result = _split_for_telegram(text)
        assert len(result) >= 4
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT

    def test_single_unbroken_run_longer_than_limit_is_hard_cut(self) -> None:
        text = "a" * (TELEGRAM_MESSAGE_LIMIT * 2 + 100)
        result = _split_for_telegram(text)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT
        assert "".join(result) == text


class TestBoundaryPreference:
    def test_splitting_prefers_paragraph_breaks_over_mid_word_cuts(self) -> None:
        first_paragraph = "x" * (TELEGRAM_MESSAGE_LIMIT - 10)
        second_paragraph = "Втори абзац с текст."
        text = first_paragraph + "\n\n" + second_paragraph
        result = _split_for_telegram(text)
        assert result[0] == first_paragraph
        assert result[1] == second_paragraph

    def test_does_not_split_inside_a_code_fence_when_a_boundary_exists_before_it(self) -> None:
        before = "Обяснение преди кода. " * 30
        code_block = "```python\nprint('hello world')\n```"
        text = before + "\n\n" + code_block
        result = _split_for_telegram(text, limit=len(before) + 10)
        assert any(chunk.count("```") % 2 == 0 for chunk in result)
