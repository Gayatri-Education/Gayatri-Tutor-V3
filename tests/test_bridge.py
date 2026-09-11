from unittest.mock import MagicMock
from app.bridge import Bridge


def test_bridge_window_controls(qtbot):
    bridge = Bridge()
    mock_window = MagicMock()
    mock_window.isMaximized.return_value = False

    bridge.set_window(mock_window)

    # Test minimize
    bridge.minimize_window()
    mock_window.showMinimized.assert_called_once()

    # Test maximize when not maximized
    bridge.maximize_window()
    mock_window.showMaximized.assert_called_once()

    # Test maximize when already maximized (should restore)
    mock_window.isMaximized.return_value = True
    bridge.maximize_window()
    mock_window.showNormal.assert_called_once()

    # Test close
    bridge.close_window()
    mock_window.close.assert_called_once()


def test_bridge_get_agents(qtbot):
    """Audit #52 & #54: bridge.get_agents returns registered agents with metadata."""
    import json
    bridge = Bridge()
    raw = bridge.get_agents()
    data = json.loads(raw)
    assert data["ok"] is True
    agent_names = [a["name"] for a in data["agents"]]
    assert "Tutor" in agent_names
    assert "Practice Generator" in agent_names
    assert "Code Reviewer" in agent_names


def test_bridge_get_curriculum_progress(qtbot, tmp_path, monkeypatch):
    """Audit #55: bridge.get_curriculum_progress returns stats and concept list."""
    import json
    from core.knowledge_graph import LearningDependencyGraph
    ldg = LearningDependencyGraph(tmp_path / "ldg.db")
    ldg.add_concept("test_concept", "Test Concept", "Description", difficulty=0.4, subject="Python")

    bridge = Bridge()
    orch = bridge._get_orchestrator()
    orch._ldg = ldg

    raw = bridge.get_curriculum_progress()
    data = json.loads(raw)
    assert data["ok"] is True
    assert "stats" in data
    assert data["stats"]["total"] >= 1
    concept_ids = [c["id"] for c in data["concepts"]]
    assert "test_concept" in concept_ids


def test_bridge_send_message_with_agent_selection(qtbot):
    """Audit #52 & #53: bridge.send_message dispatches with forced agent option."""
    bridge = Bridge()
    orch_mock = MagicMock()
    orch_mock.stream.return_value = iter([("Review feedback", True)])
    bridge._orchestrator = orch_mock

    received_tokens = []
    bridge.token.connect(lambda idx, tok: received_tokens.append(tok))

    bridge.send_message("Review this snippet", "Code Reviewer")

    orch_mock.stream.assert_called_once()
    call_args = orch_mock.stream.call_args
    assert call_args[0][0] == "Review this snippet"
    opts = call_args[1].get("options")
    assert opts is not None
    assert opts.forced_agent == "Code Reviewer"
    assert "Review feedback" in received_tokens

