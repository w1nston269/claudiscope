"""Screenshot tool: fetches the scope display as an image Claude can look at.

NOTE: the commands below are UNVERIFIED for the RTB2004. Check the RTB2000
programming manual (HCOPy subsystem) and edit these two constants if needed.
"""

from mcp.server.fastmcp import Image

SETUP_COMMANDS = ["HCOPy:LANGuage PNG"]
DATA_COMMAND = "HCOPy:DATA?"

_SIGNATURES = {b"\x89PNG": "png", b"BM": "bmp", b"GIF8": "gif", b"\xff\xd8": "jpeg"}


def _detect(data):
    for sig, fmt in _SIGNATURES.items():
        if data.startswith(sig):
            return fmt
    return None


def register(mcp, conn):
    @mcp.tool()
    def get_screenshot():
        """Capture the scope's display and return it as an image."""
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
            return f"Screenshot failed: {e}. Scope errors: {errs or 'none'}. Check the commands in tools/screenshot.py."
        finally:
            conn.inst.timeout = old_timeout
        fmt = _detect(data)
        if fmt is None:
            return f"Got {len(data)} bytes but they don't look like an image. Check the format command."
        return Image(data=data, format=fmt)
