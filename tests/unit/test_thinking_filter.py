"""Unit tests for ThinkingFilter.

Tests structured and heuristic filtering modes.
Following ТЗ-001 §65 - Unit test isolation.
"""


from src.application.proxy.core.models import FilteredResponse
from src.application.proxy.core.thinking_filter import FilterMode, ThinkingFilter


class TestThinkingFilterStructured:
    """Test structured JSON filtering mode."""

    def test_valid_json_format(self):
        """Test filtering valid structured JSON response."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)
        content = """{
  "thinking": "Посмотрю, что у нас нового в чатах.",
  "emotion": "curious",
  "response": "О, Артеллин! [joy] Давно не виделись! Как дела?"
}"""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert isinstance(result, FilteredResponse)
        assert result.content == "О, Артеллин! [joy] Давно не виделись! Как дела?"
        assert result.thinking == "Посмотрю, что у нас нового в чатах."
        assert result.emotion == "curious"

    def test_missing_fields_uses_defaults(self):
        """Test handling of missing optional fields."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)
        content = '{"response": "Hello world"}'

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.content == "Hello world"
        assert result.thinking is None
        assert result.emotion is None

    def test_invalid_json_fallback_to_heuristic(self):
        """Test fallback to heuristic when JSON parsing fails."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)
        content = "Посмотрю в базе.\nПривет, как дела?"

        # Act
        result = filter.filter_response(content)

        # Assert
        # Should fallback and filter "Посмотрю в базе."
        assert "Привет, как дела?" in result.content
        assert "Посмотрю" not in result.content

    def test_empty_response_field(self):
        """Test handling of empty response field."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)
        content = '{"thinking": "Internal", "response": ""}'

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.content == ""
        assert result.thinking == "Internal"


class TestThinkingFilterHeuristic:
    """Test heuristic pattern-based filtering mode."""

    def test_filter_russian_thinking_patterns(self):
        """Test filtering common Russian thinking patterns."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.HEURISTIC)
        content = """Посмотрю, что там у нас.
Интересно, есть ли обновления.
Привет! Как дела?
Проверю базу данных."""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert "Привет! Как дела?" in result.content
        assert "Посмотрю" not in result.content
        assert "Интересно" not in result.content
        assert "Проверю" not in result.content

    def test_extract_thinking_lines(self):
        """Test extraction of thinking lines."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.HEURISTIC)
        content = """Вспомню предыдущий разговор.
Стоит проверить контекст.
Окей, понял!"""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.thinking is not None
        assert "Вспомню" in result.thinking
        assert "Стоит проверить" in result.thinking
        assert "Окей, понял!" in result.content

    def test_emotion_tag_extraction(self):
        """Test extraction of emotion tags."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.HEURISTIC)
        content = """emotion: curious
Привет! Как дела?"""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.emotion == "curious"
        assert "emotion:" not in result.content
        assert "Привет! Как дела?" in result.content

    def test_no_thinking_patterns(self):
        """Test content without thinking patterns."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.HEURISTIC)
        content = "Привет! Рад тебя видеть!"

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.content == "Привет! Рад тебя видеть!"
        assert result.thinking is None


class TestThinkingFilterOff:
    """Test disabled filtering mode."""

    def test_passthrough_no_filtering(self):
        """Test that OFF mode returns content unchanged."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.OFF)
        content = """Посмотрю в базе данных.
Интересно, что там.
Привет!"""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert result.content == content
        assert result.thinking is None
        assert result.emotion is None


class TestThinkingFilterEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content(self):
        """Test filtering empty content."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)

        # Act
        result = filter.filter_response("")

        # Assert
        assert result.content == ""
        assert result.thinking is None

    def test_whitespace_only(self):
        """Test filtering whitespace-only content."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.HEURISTIC)

        # Act
        result = filter.filter_response("   \n\n   ")

        # Assert
        assert result.content == ""

    def test_multiline_json(self):
        """Test multiline JSON formatting."""
        # Arrange
        filter = ThinkingFilter(mode=FilterMode.STRUCTURED)
        content = """{
  "thinking": "Line 1\\nLine 2\\nLine 3",
  "response": "Response line 1\\nResponse line 2"
}"""

        # Act
        result = filter.filter_response(content)

        # Assert
        assert "Line 1" in result.thinking
        assert "Response line 1" in result.content
