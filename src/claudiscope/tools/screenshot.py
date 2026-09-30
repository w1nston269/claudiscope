"""Screenshot tool: fetches the scope display, saves it, and returns it to Claude.

Claude can see the returned image, but chat clients usually only render it inside
the tool call. So every capture is also saved to disk and can optionally be opened
in your default image viewer.

The HCOPy commands below work on the RTB2004. On another scope, check its programming
manual and edit these constants.
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


# Detach the viewer completely: the MCP server speaks over stdout, so a child process
# must never inherit it (stray output would corrupt the protocol).
_DETACHED = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, start_new_session=True)


def _open_in_viewer(path):
    """Open the file in the default viewer. Returns True if it looks like it worked.

    Claude Desktop often starts the server without the desktop session's environment
    (no DISPLAY, no DBUS address), so on Linux we fill in sensible defaults instead of
    giving up. xdg-open exits quickly with a non-zero code if it can't open anything;
    if it's still running after a few seconds, the viewer has taken over.
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
            return True
        env = os.environ.copy()
        if sys.platform == "darwin":
            cmd = ["open", str(path)]
        else:
            uid = os.getuid()
            env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
            env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
            if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
                env["DISPLAY"] = ":0"
            cmd = ["xdg-open", str(path)]
        proc = subprocess.Popen(cmd, env=env, **_DETACHED)
        try:
            return proc.wait(timeout=3) == 0
        except subprocess.TimeoutExpired:
            return True
    except Exception:
        return False


def register(mcp, conn):
    @mcp.tool()
    def get_screenshot(name: str = "", open_viewer: bool = True):
        """Capture the scope's display. Returns the image for you to look at, and saves it
        to disk. Chat clients rarely show tool images inline, so by default it also opens the
        image in the user's default viewer; pass open_viewer=False to skip that. Optional
        'name' is added to the filename (e.g. 'ch1_rising_edge'). Tell the user where the
        file was saved."""
        if not conn.connected:
            return "Not connected. Call connect() first."
        if os.environ.get("CLAUDISCOPE_NO_VIEWER"):
            open_viewer = False
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
            note = f"Saved to {path}\nFile link: {path.as_uri()}"
            if open_viewer:
                note += " (opened in viewer)" if _open_in_viewer(path) else " (could not open a viewer, open the file manually)"
        except Exception as e:
            note = f"Could not save the screenshot to disk: {e}"
        return [Image(data=data, format=fmt if fmt != "jpg" else "jpeg"), note]