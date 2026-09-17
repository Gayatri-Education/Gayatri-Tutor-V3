"""Gayatri AI — Application entry point."""

from __future__ import annotations

import os
import sys

# ── Chromium GPU flags ──────────────────────────────────────────────────────
# MUST be set before any Qt import. These flags disable the GPU process
# completely, eliminating the black-checkerboard / mosaic texture corruption
# that occurs when Windows MPO (Multi-Plane Overlay) promotes Chromium surfaces
# to hardware overlays on a frameless window with DWM composition.
#
# --disable-gpu            → Force software (SwiftShader) rendering. Eliminates
#                            all GPU texture handle corruption.
# --in-process-gpu         → No separate GPU process; runs in the browser
#                            process, removing inter-process texture sharing.
# --disable-software-rasterizer-fallback → Ensures SwiftShader is used
#                            consistently (not a mixed-path fallback).
# --disable-features=UseSkiaRenderer → Disables Skia's GPU-accelerated renderer
#                            which is the source of the mosaic corruption.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu "
    "--in-process-gpu "
    "--disable-software-rasterizer-fallback "
    "--disable-features=UseSkiaRenderer "
    "--disable-gpu-compositing "
    "--disable-gpu-rasterization "
    "--disable-zero-copy "
    "--disable-direct-composition "
    "--disable-gpu-memory-buffer-video-frames "
    "--disable-accelerated-video-decode "
    "--disable-accelerated-2d-canvas"
)

from PySide6.QtWidgets import QApplication

from core.config import WINDOW_HEIGHT, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_WIDTH
from core.logging_setup import setup_logging

logger = setup_logging(os.environ.get("GAYATRI_LOG_LEVEL", "DEBUG"))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gayatri AI")
    app.setOrganizationName("Gayatri Education")

    from app.windows.main_window import MainWindow
    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
    window.show()

    logger.info("Gayatri AI started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
