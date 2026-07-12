"""Unit tests for phoenix_core.guard.sanitizer.OutputSanitizer."""
import pytest

from phoenix_core.guard.sanitizer import MAX_TELEGRAM_MESSAGE_LENGTH, OutputSanitizer


class TestPassthrough:
    def test_short_plain_text_is_unchanged(self) -> None:
        sanitizer = OutputSanitizer()
        assert sanitizer.sanitize("Здравей, свят!") == "Здравей, свят!"

    def test_balanced_markdown_tokens_unchanged(self) -> None:
        sanitizer = OutputSanitizer()
        text = "Ползвай *bold* и `code` тук."
        assert sanitizer.sanitize(text) == text


class TestMarkdownBalancing:
    def test_odd_asterisk_gets_closed(self) -> None:
        sanitizer = OutputSanitizer()
        result = sanitizer.sanitize("това е *незатворено")
        assert result.count("*") % 2 == 0

    def test_odd_backtick_gets_closed(self) -> None:
        sanitizer = OutputSanitizer()
        result = sanitizer.sanitize("код: `print(1)")
        assert result.count("`") % 2 == 0

    def test_odd_underscore_gets_closed(self) -> None:
        sanitizer = OutputSanitizer()
        result = sanitizer.sanitize("_italic without close")
        assert result.count("_") % 2 == 0

    def test_unclosed_code_fence_gets_closed(self) -> None:
        sanitizer = OutputSanitizer()
        result = sanitizer.sanitize("```python\nprint(1)\n")
        assert result.count("```") % 2 == 0


class TestTruncation:
    def test_text_within_limit_unchanged(self) -> None:
        sanitizer = OutputSanitizer(max_length=100)
        text = "a" * 50
        assert sanitizer.sanitize(text) == text

    def test_text_over_limit_is_truncated_with_marker(self) -> None:
        sanitizer = OutputSanitizer(max_length=100)
        text = "a" * 500
        result = sanitizer.sanitize(text)
        assert len(result) <= 100
        assert "съкратено" in result

    def test_truncated_result_never_exceeds_max_length(self) -> None:
        sanitizer = OutputSanitizer(max_length=MAX_TELEGRAM_MESSAGE_LENGTH)
        text = "х" * 10000
        result = sanitizer.sanitize(text)
        assert len(result) <= MAX_TELEGRAM_MESSAGE_LENGTH


class TestConstruction:
    def test_too_small_max_length_rejected(self) -> None:
        with pytest.raises(ValueError):
            OutputSanitizer(max_length=1)


class TestHealthCheck:
    async def test_reports_configured_limit(self) -> None:
        sanitizer = OutputSanitizer(max_length=2000)
        health = await sanitizer.health_check()
        assert health == {"max_length": 2000}
