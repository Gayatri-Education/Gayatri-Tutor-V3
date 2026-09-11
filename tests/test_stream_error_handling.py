import pytest
from unittest.mock import MagicMock
from core.orchestrator import Orchestrator
from app.bridge import Bridge


def test_stream_error_does_not_persist_error_as_assistant_message(monkeypatch):
    """Audit #17: Verify conversation history is not contaminated with error text."""
    orch = Orchestrator()
    session_id = "test_err_sess_1"

    # Force LocalProvider.chat_stream to fail
    def failing_stream(*args, **kwargs):
        raise ConnectionError("Provider failed to connect")

    monkeypatch.setattr("core.providers.local.LocalProvider.chat_stream", failing_stream)

    # Calling stream should raise an error
    with pytest.raises(RuntimeError, match="Streaming failed"):
        list(orch.stream("Hello world", session_id=session_id))

    # Inspect conversation
    conv = orch.get_conversation(session_id)
    messages = conv.get_all()

    # User message should be recorded
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello world"

    # Ensure NO assistant message containing raw error text was stored
    for msg in messages:
        assert msg["role"] != "assistant"
        assert "Provider failed to connect" not in msg["content"]


def test_stream_emits_single_terminal_event_on_failure(monkeypatch, qtbot):
    """Audit #18: Verify bridge emits done exactly once and emits error on failure."""
    bridge = Bridge()
    orch = bridge._get_orchestrator()

    def failing_stream(*args, **kwargs):
        raise ConnectionError("Model crashed")

    monkeypatch.setattr("core.providers.local.LocalProvider.chat_stream", failing_stream)

    done_calls = []
    error_calls = []

    bridge.done.connect(lambda: done_calls.append(True))
    bridge.error.connect(lambda err: error_calls.append(err))

    bridge.send_message("Test failure")

    # Exactly one error and one done
    assert len(error_calls) == 1
    assert "Model crashed" in error_calls[0]
    assert len(done_calls) == 1


def test_submit_error_does_not_persist_error_as_assistant_message(monkeypatch):
    """Audit #17: Verify submit does not store raw exception text as assistant message."""
    orch = Orchestrator()
    session_id = "test_err_sess_2"

    def failing_chat(*args, **kwargs):
        raise ConnectionError("Local provider down")

    monkeypatch.setattr("core.providers.local.LocalProvider.chat", failing_chat)

    res = orch.submit("Calculate this", session_id=session_id)
    assert "error" in res.routing_reason

    # Check conversation
    conv = orch.get_conversation(session_id)
    messages = conv.get_all()

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Calculate this"

    for msg in messages:
        assert msg["role"] != "assistant"
