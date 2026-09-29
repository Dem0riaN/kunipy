"""Tests for text-based tool call parser."""


from src.infrastructure.tool_call_parser import (
    ToolCallParser,
    extract_thinking_and_calls,
    parse_text_tool_calls,
)


class TestToolCallParser:
    """Test ToolCallParser class."""

    def test_parse_single_tool_call(self):
        """Parser extracts single tool call from text."""
        parser = ToolCallParser()
        text = 'send_telegram_message({"text": "Hello!"})'

        calls = parser.parse_text_tool_calls(text)

        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "send_telegram_message"
        assert calls[0]["function"]["arguments"] == '{"text": "Hello!"}'
        assert "id" in calls[0]

    def test_parse_multiple_tool_calls(self):
        """Parser extracts multiple tool calls from text."""
        parser = ToolCallParser()
        text = '''
        open_chat_by_id({"chat_id": 123})
        send_telegram_message({"text": "Hi there!"})
        '''

        calls = parser.parse_text_tool_calls(text)

        assert len(calls) == 2
        assert calls[0]["function"]["name"] == "open_chat_by_id"
        assert calls[1]["function"]["name"] == "send_telegram_message"

    def test_parse_tool_call_with_multiline_json(self):
        """Parser handles tool calls with multiline JSON arguments."""
        parser = ToolCallParser()
        text = 'send_telegram_message({"text": "Line 1\\nLine 2"})'

        calls = parser.parse_text_tool_calls(text)

        assert len(calls) == 1
        assert '"text": "Line 1\\nLine 2"' in calls[0]["function"]["arguments"]

    def test_parse_empty_text(self):
        """Parser returns empty list for empty text."""
        parser = ToolCallParser()

        calls = parser.parse_text_tool_calls("")

        assert calls == []

    def test_parse_text_without_tool_calls(self):
        """Parser returns empty list when no tool calls found."""
        parser = ToolCallParser()
        text = "Just some thinking text without any function calls."

        calls = parser.parse_text_tool_calls(text)

        assert calls == []

    def test_skip_malformed_json(self):
        """Parser skips tool calls with invalid JSON."""
        parser = ToolCallParser()
        text = 'send_telegram_message({"text": "unclosed string})'

        calls = parser.parse_text_tool_calls(text)

        # Malformed JSON should be skipped
        assert len(calls) == 0

    def test_extract_thinking_and_calls(self):
        """Parser separates thinking text from tool calls."""
        parser = ToolCallParser()
        text = '''
        - thought: I should reply
        - emotion: happy

        send_telegram_message({"text": "Hi!"})
        '''

        thinking, calls = parser.extract_thinking_and_calls(text)

        assert "thought: I should reply" in thinking
        assert "emotion: happy" in thinking
        assert "send_telegram_message" not in thinking
        assert len(calls) == 1

    def test_extract_thinking_only(self):
        """Parser returns all text as thinking when no tool calls."""
        parser = ToolCallParser()
        text = "Just thinking about the problem..."

        thinking, calls = parser.extract_thinking_and_calls(text)

        assert thinking == "Just thinking about the problem..."
        assert calls == []

    def test_is_text_based_tool_call(self):
        """Detector identifies text-based tool calls."""
        parser = ToolCallParser()

        assert parser.is_text_based_tool_call('send_telegram_message({"text": "Hi"})')
        assert parser.is_text_based_tool_call('open_chat_by_id({"chat_id": 123})')
        assert not parser.is_text_based_tool_call("Just thinking...")
        assert not parser.is_text_based_tool_call("")

    def test_parse_tool_call_with_numbers(self):
        """Parser handles tool calls with numeric arguments."""
        parser = ToolCallParser()
        text = 'open_chat_by_id({"chat_id": 368307238})'

        calls = parser.parse_text_tool_calls(text)

        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "open_chat_by_id"
        assert "368307238" in calls[0]["function"]["arguments"]

    def test_convenience_function_parse_text_tool_calls(self):
        """Convenience function works without creating parser instance."""
        calls = parse_text_tool_calls('send_telegram_message({"text": "Test"})')

        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "send_telegram_message"

    def test_convenience_function_extract_thinking_and_calls(self):
        """Convenience function extracts thinking and calls."""
        text = 'Thinking...\\nsend_telegram_message({"text": "Hi"})'

        thinking, calls = extract_thinking_and_calls(text)

        assert "Thinking..." in thinking
        assert len(calls) == 1


class TestRealWorldScenarios:
    """Test real-world scenarios from DeepSeek-R1."""

    def test_deepseek_r1_output_format(self):
        """Parser handles typical DeepSeek-R1 output."""
        text = '''- thought: Artellin is offering to give me books to read. This is a friendly, casual offer. I should respond playfully and positively.
- emotion: happy, curious
- to remember: Artellin likes to recommend books
- intention: Respond to Artellin's offer with enthusiasm

send_telegram_message({"text": "О, это заманчиво! 😊 Что предлагаешь?"})'''

        thinking, calls = extract_thinking_and_calls(text)

        # Thinking should contain thoughts but not the tool call
        assert "thought:" in thinking
        assert "emotion:" in thinking
        assert "send_telegram_message" not in thinking

        # Tool call should be extracted
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "send_telegram_message"
        assert "О, это заманчиво!" in calls[0]["function"]["arguments"]

    def test_multiple_actions_scenario(self):
        """Parser handles multiple sequential actions."""
        text = '''- thought: I need to open the chat first
- intention: Open chat and reply

open_chat_by_id({"chat_id": 368307238})
send_telegram_message({"text": "Извини за задержку!"})'''

        thinking, calls = extract_thinking_and_calls(text)

        assert len(calls) == 2
        assert calls[0]["function"]["name"] == "open_chat_by_id"
        assert calls[1]["function"]["name"] == "send_telegram_message"
        assert "open_chat_by_id" not in thinking
        assert "send_telegram_message" not in thinking
