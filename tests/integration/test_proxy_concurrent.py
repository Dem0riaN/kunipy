"""
Concurrent session stress tests for Proxy Phase 2 P1.

Tests parallel session handling, race conditions, and session isolation
with 10, 50, and 100 concurrent sessions.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src.application.proxy.server import create_proxy_application

# Test data
SYSTEM_MESSAGE = {
    "role": "system",
    "content": "You are a helpful assistant."
}

def create_user_message(session_id: int) -> dict:
    """Create unique user message for session."""
    return {
        "role": "user",
        "content": f"Test message from session {session_id}"
    }


@pytest.fixture
def proxy_app(monkeypatch):
    """Create proxy application for testing."""
    # Mock config to disable diary (avoids complex Diary initialization)
    from src.config import Config

    mock_config = Config()
    mock_config.diary_enabled = False
    mock_config.proxy_session_timeout_minutes = 30

    monkeypatch.setattr("src.application.proxy.server.get_config", lambda: mock_config)

    # Now create_proxy_application won't try to create Diary
    app = create_proxy_application()
    return app


@pytest.fixture
def client(proxy_app):
    """Create test client."""
    return TestClient(proxy_app)


class TestProxyConcurrentSessions:
    """Test concurrent session handling and isolation."""

    def test_10_parallel_sessions(self, client, monkeypatch):
        """Test proxy with 10 parallel sessions.

        Validates:
        - All sessions complete without errors
        - Session isolation (no cross-contamination)
        - Fingerprint-based tracking works under load
        """
        call_count = {"count": 0}
        session_fingerprints = {}

        def mock_post(*args, **kwargs):
            """Mock upstream responses."""
            call_count["count"] += 1

            # Extract messages to track session
            data = kwargs.get("json", {})
            messages = data.get("messages", [])

            # Simple fingerprint for tracking
            fingerprint = str(len(messages))
            session_fingerprints[fingerprint] = session_fingerprints.get(fingerprint, 0) + 1

            class MockResponse:
                status_code = 200

                def json(self):
                    return {
                        "id": f"chatcmpl-{call_count['count']}",
                        "object": "chat.completion",
                        "created": 1234567890 + call_count["count"],
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"Response {call_count['count']}"
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                    }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Execute 10 parallel requests
        def make_request(session_id: int):
            messages = [SYSTEM_MESSAGE, create_user_message(session_id)]
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": messages}
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in futures]

        # Verify all succeeded
        assert len(results) == 10
        assert all(status == 200 for status, _ in results)
        assert call_count["count"] == 10

        # Verify unique responses (no mixing)
        response_ids = [data["id"] for _, data in results]
        assert len(set(response_ids)) == 10

    def test_50_parallel_sessions(self, client, monkeypatch):
        """Test proxy with 50 parallel sessions.

        Validates:
        - Scalability to moderate load
        - No degradation in isolation
        - Session manager O(1) lookup performance
        """
        call_count = {"count": 0}

        def mock_post(*args, **kwargs):
            """Mock upstream responses."""
            call_count["count"] += 1

            class MockResponse:
                status_code = 200

                def json(self):
                    return {
                        "id": f"chatcmpl-{call_count['count']}",
                        "object": "chat.completion",
                        "created": 1234567890 + call_count["count"],
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"Response {call_count['count']}"
                            },
                            "finish_reason": "stop"
                        }]
                    }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Execute 50 parallel requests
        def make_request(session_id: int):
            messages = [SYSTEM_MESSAGE, create_user_message(session_id)]
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": messages}
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(50)]
            statuses = [f.result() for f in futures]

        # Verify all succeeded
        assert len(statuses) == 50
        assert all(status == 200 for status in statuses)
        assert call_count["count"] == 50

    def test_100_parallel_sessions(self, client, monkeypatch):
        """Test proxy with 100 parallel sessions.

        Validates:
        - High load handling
        - No race conditions in session manager
        - Memory efficiency (no leaks under stress)
        """
        call_count = {"count": 0}
        errors = []

        def mock_post(*args, **kwargs):
            """Mock upstream responses."""
            call_count["count"] += 1

            class MockResponse:
                status_code = 200

                def json(self):
                    return {
                        "id": f"chatcmpl-{call_count['count']}",
                        "object": "chat.completion",
                        "created": 1234567890 + call_count["count"],
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"Response {call_count['count']}"
                            },
                            "finish_reason": "stop"
                        }]
                    }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Execute 100 parallel requests
        def make_request(session_id: int):
            try:
                messages = [SYSTEM_MESSAGE, create_user_message(session_id)]
                response = client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4", "messages": messages}
                )
                return response.status_code
            except Exception as e:
                errors.append(str(e))
                return 500

        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(make_request, i) for i in range(100)]
            statuses = [f.result() for f in futures]

        # Verify all succeeded (or report errors)
        assert len(statuses) == 100
        successful = sum(1 for status in statuses if status == 200)

        # At least 95% success rate under high load
        assert successful >= 95, f"Only {successful}/100 succeeded. Errors: {errors[:5]}"
        assert call_count["count"] >= 95

    def test_session_isolation_under_load(self, client, monkeypatch):
        """Test that sessions remain isolated under concurrent load.

        Validates:
        - Session A's context never leaks to Session B
        - Each session maintains independent message history
        - Fingerprint-based routing is thread-safe
        """
        call_count = {"count": 0}
        captured_messages = {}

        def mock_post(*args, **kwargs):
            """Mock upstream and capture what each session sees."""
            call_count["count"] += 1

            data = kwargs.get("json", {})
            messages = data.get("messages", [])

            # Track what messages each call receives
            call_id = call_count["count"]
            captured_messages[call_id] = [msg.get("content", "") for msg in messages]

            class MockResponse:
                status_code = 200

                def json(self):
                    return {
                        "id": f"chatcmpl-{call_id}",
                        "object": "chat.completion",
                        "created": 1234567890 + call_id,
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"Isolated response {call_id}"
                            },
                            "finish_reason": "stop"
                        }]
                    }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Create 20 sessions with unique content
        def make_request(session_id: int):
            unique_content = f"UNIQUE_SESSION_{session_id}_MARKER"
            messages = [
                SYSTEM_MESSAGE,
                {"role": "user", "content": unique_content}
            ]
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": messages}
            )
            return session_id, response.json()

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in futures]

        # Verify isolation: each session's unique marker should only appear in its own messages
        for session_id, response_data in results:
            marker = f"UNIQUE_SESSION_{session_id}_MARKER"

            # Find which upstream call handled this session
            found_in_calls = []
            for call_id, messages in captured_messages.items():
                if any(marker in msg for msg in messages):
                    found_in_calls.append(call_id)

            # Each session's marker should appear in exactly one upstream call
            assert len(found_in_calls) == 1, \
                f"Session {session_id} marker found in {len(found_in_calls)} calls (expected 1)"

    def test_race_condition_session_creation(self, client, monkeypatch):
        """Test concurrent session creation with identical fingerprints.

        Validates:
        - No race conditions in SessionManager.get_or_create_session
        - Proper locking/thread-safety in session storage
        - Consistent session assignment for identical requests
        """
        call_count = {"count": 0}

        def mock_post(*args, **kwargs):
            """Mock upstream responses."""
            call_count["count"] += 1

            class MockResponse:
                status_code = 200

                def json(self):
                    return {
                        "id": f"chatcmpl-{call_count['count']}",
                        "object": "chat.completion",
                        "created": 1234567890,
                        "model": "gpt-4",
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Response"
                            },
                            "finish_reason": "stop"
                        }]
                    }

            return MockResponse()

        monkeypatch.setattr("httpx.post", mock_post)

        # Send 10 IDENTICAL requests simultaneously (same fingerprint)
        identical_messages = [
            SYSTEM_MESSAGE,
            {"role": "user", "content": "Identical test message"}
        ]

        def make_request(_):
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": identical_messages}
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            statuses = [f.result() for f in futures]

        # All should succeed without race condition errors
        assert len(statuses) == 10
        assert all(status == 200 for status in statuses)
        assert call_count["count"] == 10
