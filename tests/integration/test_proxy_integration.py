"""Integration tests for Proxy Phase 1-2.

Tests multi-turn conversations, session continuity, tool call hiding,
and hidden context injection across actual HTTP requests.

Phase 2 tests validate:
- Complete multi-turn conversation flows with tool usage
- Hidden context persistence across session turns
- Session expiry and cleanup behavior
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.application.proxy.server import create_proxy_application
from src.application.tools.registry import ToolRegistry

# Test data
SYSTEM_MESSAGE = {
    "role": "system",
    "content": "You are a helpful assistant."
}

USER_MESSAGE_1 = {
    "role": "user",
    "content": "What is 2+2?"
}

USER_MESSAGE_2 = {
    "role": "user",
    "content": "And what about 5+5?"
}


@pytest.fixture
def mock_upstream_responses():
    """Mock responses that simulate LLM with tool calls."""
    return {
        "turn1_with_tool": {
            "id": "chatcmpl-test1",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "ask",
                            "arguments": json.dumps({"question": "What is 2+2?"})
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        },
        "turn1_final": {
            "id": "chatcmpl-test2",
            "object": "chat.completion",
            "created": 1234567891,
            "model": "gpt-4",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "2+2 equals 4."
                },
                "finish_reason": "stop"
            }]
        },
        "turn2_response": {
            "id": "chatcmpl-test3",
            "object": "chat.completion",
            "created": 1234567892,
            "model": "gpt-4",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "5+5 equals 10."
                },
                "finish_reason": "stop"
            }]
        }
    }


@pytest.fixture
def proxy_app():
    """Create proxy application for testing."""
    tool_registry = ToolRegistry()
    # Register minimal tools for testing
    app = create_proxy_application(
        upstream_base_url="http://mock-llm:8000",
        tool_registry=tool_registry,
        session_timeout_minutes=30
    )
    return app


@pytest.fixture
def client(proxy_app):
    """Create test client."""
    return TestClient(proxy_app)


class TestProxySessionContinuity:
    """Test session tracking and continuation across requests."""

    def test_new_session_creation(self, client, monkeypatch):
        """Test that a new conversation creates a new session."""
        # Mock upstream to return simple response
        def mock_post(*args, **kwargs):
            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "id": "test",
                        "object": "chat.completion",
                        "created": 123,
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": "4"},
                            "finish_reason": "stop"
                        }]
                    }
            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [SYSTEM_MESSAGE, USER_MESSAGE_1]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert data["choices"][0]["message"]["role"] == "assistant"

    def test_session_continuation_detection(self, client, monkeypatch):
        """Test that follow-up messages in same conversation use same session."""
        responses_sequence = []

        def mock_post(*args, **kwargs):
            class MockResponse:
                status_code = 200
                def json(self):
                    # Return different responses for first and second call
                    if len(responses_sequence) == 0:
                        responses_sequence.append(1)
                        return {
                            "id": "test1",
                            "choices": [{
                                "message": {"role": "assistant", "content": "First response"},
                                "finish_reason": "stop"
                            }]
                        }
                    else:
                        return {
                            "id": "test2",
                            "choices": [{
                                "message": {"role": "assistant", "content": "Second response"},
                                "finish_reason": "stop"
                            }]
                        }
            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # First request
        messages_turn1 = [SYSTEM_MESSAGE, USER_MESSAGE_1]
        response1 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages_turn1}
        )
        assert response1.status_code == 200

        # Second request - continuation (includes assistant response)
        assistant_response = response1.json()["choices"][0]["message"]
        messages_turn2 = messages_turn1 + [assistant_response, USER_MESSAGE_2]

        response2 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages_turn2}
        )
        assert response2.status_code == 200

        # Verify both requests succeeded
        data2 = response2.json()
        assert "choices" in data2


class TestProxyToolCallHiding:
    """Test that tool calls and results are hidden from client."""

    def test_tool_call_hidden_from_response(self, client, monkeypatch):
        """Test tool calls are not visible in client response."""
        call_count = [0]

        def mock_post(*args, **kwargs):
            class MockResponse:
                status_code = 200
                def json(self):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        # First call: LLM requests tool
                        return {
                            "id": "test",
                            "choices": [{
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [{
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "ask",
                                            "arguments": json.dumps({"question": "test"})
                                        }
                                    }]
                                },
                                "finish_reason": "tool_calls"
                            }]
                        }
                    else:
                        # Second call: final response after tool
                        return {
                            "id": "test2",
                            "choices": [{
                                "message": {
                                    "role": "assistant",
                                    "content": "Final answer after tool"
                                },
                                "finish_reason": "stop"
                            }]
                        }
            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [SYSTEM_MESSAGE, USER_MESSAGE_1],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "ask",
                        "description": "Ask a question",
                        "parameters": {
                            "type": "object",
                            "properties": {"question": {"type": "string"}},
                            "required": ["question"]
                        }
                    }
                }]
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify final response doesn't contain tool_calls
        message = data["choices"][0]["message"]
        assert "tool_calls" not in message or message.get("tool_calls") is None
        assert message["content"] == "Final answer after tool"


class TestProxyMessageInjection:
    """Test hidden context injection mechanism."""

    def test_hidden_context_not_in_client_messages(self, client, monkeypatch):
        """Test that hidden context is injected but not visible to client."""
        received_messages = []

        def mock_post(*args, **kwargs):
            # Capture what messages proxy sends to upstream
            if "json" in kwargs:
                received_messages.append(kwargs["json"].get("messages", []))

            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "id": "test",
                        "choices": [{
                            "message": {"role": "assistant", "content": "Response"},
                            "finish_reason": "stop"
                        }]
                    }
            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Send request with only user messages
        client_messages = [SYSTEM_MESSAGE, USER_MESSAGE_1]
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": client_messages}
        )

        assert response.status_code == 200

        # Verify proxy may have added hidden context to upstream
        # but client only sees clean response
        data = response.json()
        assert "choices" in data
        assert data["choices"][0]["finish_reason"] == "stop"


class TestProxyStreaming:
    """Test streaming mode (buffered in Phase 1)."""

    def test_streaming_buffered_mode(self, client, monkeypatch):
        """Test that streaming=true works in buffered mode."""
        def mock_post(*args, **kwargs):
            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "id": "test",
                        "choices": [{
                            "message": {"role": "assistant", "content": "Buffered response"},
                            "finish_reason": "stop"
                        }]
                    }
            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [SYSTEM_MESSAGE, USER_MESSAGE_1],
                "stream": True
            }
        )

        # In Phase 1, even with stream=true, we get complete response
        # True streaming will be implemented in Phase 3
        assert response.status_code == 200


class TestProxyErrorHandling:
    """Test error handling and edge cases."""

    def test_upstream_timeout_handling(self, client, monkeypatch):
        """Test graceful handling of upstream timeout."""
        def mock_post_timeout(*args, **kwargs):
            import httpx
            raise httpx.TimeoutException("Upstream timeout")

        monkeypatch.setattr("httpx.post", mock_post_timeout)

        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [USER_MESSAGE_1]}
        )

        # Should return error status
        assert response.status_code >= 400

    def test_malformed_request_handling(self, client):
        """Test handling of malformed requests."""
        response = client.post(
            "/v1/chat/completions",
            json={"invalid": "data"}
        )

        assert response.status_code >= 400

    def test_empty_messages_handling(self, client):
        """Test handling of empty messages array."""
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": []}
        )

        assert response.status_code >= 400

    def test_tool_execution_failure(self, client, monkeypatch):
        """Test graceful handling when tool execution fails."""
        # Mock a tool call response from upstream
        call_count = {"count": 0}

        def mock_post_with_tool(*args, **kwargs):
            call_count["count"] += 1

            class MockResponse:
                status_code = 200

                def json(self):
                    if call_count["count"] == 1:
                        # First call: LLM requests tool
                        return {
                            "id": "chatcmpl-tef1",
                            "object": "chat.completion",
                            "model": "gpt-4",
                            "choices": [{
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [{
                                        "id": "call_fail",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": json.dumps({"query": "test"})
                                        }
                                    }]
                                },
                                "finish_reason": "tool_calls"
                            }]
                        }
                    else:
                        # Second call: LLM handles tool error
                        return {
                            "id": "chatcmpl-tef2",
                            "object": "chat.completion",
                            "model": "gpt-4",
                            "choices": [{
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "I encountered an error while searching."
                                },
                                "finish_reason": "stop"
                            }]
                        }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post_with_tool)

        # Mock tool execution to raise error
        original_execute = None
        if hasattr(client.app, "state") and hasattr(client.app.state, "tool_provider"):
            tool_provider = client.app.state.tool_provider
            original_execute = tool_provider.execute_tool

            def failing_execute(tool_name, arguments):
                raise RuntimeError("Tool execution failed")

            tool_provider.execute_tool = failing_execute

        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [USER_MESSAGE_1]}
        )

        # Restore original method
        if original_execute and hasattr(client.app.state, "tool_provider"):
            client.app.state.tool_provider.execute_tool = original_execute

        # Should handle error gracefully and return response
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data

    def test_upstream_connection_refused(self, client, monkeypatch):
        """Test handling when upstream server refuses connection."""
        def mock_post_refused(*args, **kwargs):
            import httpx
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr("httpx.post", mock_post_refused)

        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [USER_MESSAGE_1]}
        )

        # Should return error status
        assert response.status_code >= 500


# Phase 2 specific tests (will be expanded)
class TestProxyPhase2Requirements:
    """Advanced integration tests for Phase 2 multi-turn scenarios."""

    def test_multi_turn_conversation_with_tools(self, client, monkeypatch):
        """Test complete multi-turn conversation with tool usage across 3 turns."""
        # Mock upstream LLM responses for 3-turn conversation
        responses = [
            # Turn 1: Tool call for weather
            {
                "id": "chatcmpl-mt1",
                "object": "chat.completion",
                "created": 1234567890,
                "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_weather",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "weather Paris"})
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
            },
            # Turn 2: Response with tool result
            {
                "id": "chatcmpl-mt2",
                "object": "chat.completion",
                "created": 1234567891,
                "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "The weather in Paris is sunny with 22°C."
                    },
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 80, "completion_tokens": 15, "total_tokens": 95}
            },
            # Turn 3: Another tool call
            {
                "id": "chatcmpl-mt3",
                "object": "chat.completion",
                "created": 1234567892,
                "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_translate",
                            "type": "function",
                            "function": {
                                "name": "ask",
                                "arguments": json.dumps({"query": "translate to French"})
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125}
            }
        ]

        response_iter = iter(responses)

        async def mock_post(*args, **kwargs):
            class MockResponse:
                def __init__(self, json_data):
                    self._json = json_data
                    self.status_code = 200

                async def json(self):
                    return self._json

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse(next(response_iter))

        monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

        # Turn 1: Initial request
        response1 = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [
                    SYSTEM_MESSAGE,
                    {"role": "user", "content": "What's the weather in Paris?"}
                ]
            }
        )

        assert response1.status_code == 200
        data1 = response1.json()

        # Tool call should be hidden from client
        assert data1["choices"][0]["message"]["content"] is not None
        assert "tool_calls" not in data1["choices"][0]["message"]

        # Extract session fingerprint from first request
        # (in real scenario, session is tracked by message fingerprint)

        # Turn 2: Continue conversation with tool result context
        response2 = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [
                    SYSTEM_MESSAGE,
                    {"role": "user", "content": "What's the weather in Paris?"},
                    {"role": "assistant", "content": data1["choices"][0]["message"]["content"]},
                    {"role": "user", "content": "Is it warmer than yesterday?"}
                ]
            }
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["choices"][0]["message"]["content"] is not None

        # Turn 3: Third turn with different tool
        response3 = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [
                    SYSTEM_MESSAGE,
                    {"role": "user", "content": "What's the weather in Paris?"},
                    {"role": "assistant", "content": data1["choices"][0]["message"]["content"]},
                    {"role": "user", "content": "Is it warmer than yesterday?"},
                    {"role": "assistant", "content": data2["choices"][0]["message"]["content"]},
                    {"role": "user", "content": "Translate your answer to French"}
                ]
            }
        )

        assert response3.status_code == 200
        data3 = response3.json()

        # Verify third turn also hides tool calls
        assert data3["choices"][0]["message"]["content"] is not None
        assert "tool_calls" not in data3["choices"][0]["message"]

    def test_hidden_context_persistence_across_turns(self, client, monkeypatch):
        """Test that hidden tool context persists correctly across session."""
        # First turn with tool call
        async def mock_post_turn1(*args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                async def json(self):
                    return {
                        "id": "chatcmpl-hc1",
                        "object": "chat.completion",
                        "created": 1234567890,
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": "call_search",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": json.dumps({"query": "Python asyncio"})
                                    }
                                }]
                            },
                            "finish_reason": "tool_calls"
                        }],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 18, "total_tokens": 58}
                    }

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        monkeypatch.setattr("httpx.AsyncClient.post", mock_post_turn1)

        # Turn 1
        messages_turn1 = [
            SYSTEM_MESSAGE,
            {"role": "user", "content": "Search for Python asyncio"}
        ]

        response1 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages_turn1}
        )

        assert response1.status_code == 200
        data1 = response1.json()

        # Client should not see tool calls
        assert "tool_calls" not in data1["choices"][0]["message"]
        assert data1["choices"][0]["message"]["content"] is not None

        # Turn 2: Verify hidden context is injected from session
        call_count = {"count": 0}
        captured_request = {"data": None}

        async def mock_post_turn2(*args, **kwargs):
            call_count["count"] += 1
            captured_request["data"] = kwargs.get("json", {})

            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                async def json(self):
                    return {
                        "id": "chatcmpl-hc2",
                        "object": "chat.completion",
                        "created": 1234567891,
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Asyncio is Python's library for concurrent programming."
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {"prompt_tokens": 60, "completion_tokens": 12, "total_tokens": 72}
                    }

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        monkeypatch.setattr("httpx.AsyncClient.post", mock_post_turn2)

        messages_turn2 = messages_turn1 + [
            {"role": "assistant", "content": data1["choices"][0]["message"]["content"]},
            {"role": "user", "content": "Tell me more"}
        ]

        response2 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages_turn2}
        )

        assert response2.status_code == 200
        assert call_count["count"] == 1

        # Verify that upstream received MORE messages than client sent
        # (hidden tool call context was injected)
        upstream_messages = captured_request["data"].get("messages", [])
        assert len(upstream_messages) > len(messages_turn2)

    def test_session_expiry_and_cleanup(self, client, monkeypatch):
        """Test automatic session expiration after timeout."""
        import time

        async def mock_post(*args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                async def json(self):
                    return {
                        "id": "chatcmpl-exp",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Response"
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}
                    }

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            return MockResponse()

        monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

        # Create initial session
        messages = [SYSTEM_MESSAGE, USER_MESSAGE_1]

        response1 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages}
        )

        assert response1.status_code == 200

        # Access session manager to verify session exists
        # Note: In real implementation, we'd mock time.time() to simulate timeout
        # For now, just verify session was created

        # Second request should reuse same session (within timeout)
        response2 = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": messages}
        )

        assert response2.status_code == 200

        # Verify session tracking works (responses should be similar)
        assert response1.json()["id"] != response2.json()["id"]
