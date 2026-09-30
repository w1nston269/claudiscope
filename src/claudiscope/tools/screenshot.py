"""Screenshot tool: fetches the scope display, saves it, and returns it to Claude.

Claude can see the returned image, but chat clients usually only render it inside
the tool call. So every capture is also saved to disk and can optionally be opened
in your default image viewer.

NOTE: the scope commands below are UNVERIFIED for the RTB2004. Check the RTB2000
programming manual (HCOPy subsystem) and edit these constants if needed.
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import Image

SETUP_COMMANDS = ["HCOPy:LANGuage PNG"]
DATA_COMMAND = "HCOPy:DATA?"
SAVE_DIR = Path.home() / "claudiscope-screenshots"

_SIGNATURES = {b"\x89PNG": "png", b"BM": "bmp", b"GIF8": "gif", b"\xff\xd8": "jpg"}


def _detect(data):
    for sig, fmt in _SIGNATURES.items():
        if data.startswith(sig):
            return fmt
    return None


def _save(data, fmt, name):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") if name else ""
    path = SAVE_DIR / f"{stamp}{'-' + label if label else ''}.{fmt}"
    path.write_bytes(data)
    return path


def _open_in_viewer(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def register(mcp, conn):
    @mcp.tool()
    def get_screenshot(name: str = "", open_viewer: bool = False):
        """Capture the scope's display. Returns the image for you to look at, and saves it
        to disk. Optional 'name' is added to the filename (e.g. 'ch1_rising_edge').
        Set open_viewer=True when the user wants to see the screenshot themselves: it opens
        in their default image viewer. Tell the user where the file was saved."""
        if not conn.connected:
            return "Not connected. Call connect() first."
        old_timeout = conn.inst.timeout
        conn.inst.timeout = 30000
        try:
            for cmd in SETUP_COMMANDS:
                conn.write(cmd)
            data = conn.read_binary(DATA_COMMAND)
        except Exception as e:
            try:
                errs = conn.errors()
            except Exception:
                errs = []
            return (f"Screenshot failed: {e}. Scope errors: {errs or 'none'}. "
                    "Check the commands in tools/screenshot.py.")
        finally:
            conn.inst.timeout = old_timeout

        fmt = _detect(data)
        if fmt is None:
            return f"Got {len(data)} bytes but they don't look like an image. Check the format command."

        note = ""
        try:
            path = _save(data, fmt, name)
            note = f"Saved to {path}"
            if open_viewer:
                note += " (opened in viewer)" if _open_in_viewer(path) else " (could not open a viewer)"
        except Exception as e:
            note = f"Could not save the screenshot to disk: {e}"
        return [Image(data=data, format=fmt if fmt != "jpg" else "jpeg"), note]