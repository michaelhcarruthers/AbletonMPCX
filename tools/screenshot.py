"""Screenshot tool — capture screen for visual analysis."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time


def take_screenshot(region: str = "full", save_path: str = None) -> dict:
    """Take a screenshot of the Ableton Live window for visual analysis."""
    import sys

    timestamp = time.time()
    if save_path is None:
        save_path = os.path.join(
            tempfile.gettempdir(),
            "abletonmpcx_screenshot_{:.0f}.png".format(timestamp),
        )

    save_path = str(save_path)
    error = None
    width = 0
    height = 0

    try:
        captured = False

        # macOS: use screencapture (no user interaction needed with -x flag)
        if sys.platform == "darwin":
            result = subprocess.run(
                ["screencapture", "-x", save_path],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and os.path.exists(save_path):
                captured = True

        # Fallback: try PIL.ImageGrab (cross-platform)
        if not captured:
            try:
                from PIL import ImageGrab  # type: ignore
                img = ImageGrab.grab()
                img.save(save_path)
                captured = True
            except ImportError:
                pass

        if not captured:
            raise RuntimeError(
                "Screenshot capture failed: screencapture unavailable and PIL not installed."
            )

        # Read dimensions if PIL is available
        try:
            from PIL import Image  # type: ignore
            with Image.open(save_path) as img:
                width, height = img.size
        except ImportError:
            pass

        return {
            "image_path": save_path,
            "region": region,
            "width": width,
            "height": height,
            "timestamp": timestamp,
            "success": True,
            "error": None,
        }

    except Exception as exc:
        error = str(exc)
        return {
            "image_path": save_path,
            "region": region,
            "width": width,
            "height": height,
            "timestamp": timestamp,
            "success": False,
            "error": error,
        }
