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
