"""Raw SCPI passthrough tools, guarded by safety.py."""

from claudiscope import safety


def _error_note(conn):
    try:
        errs = conn.errors()
    except Exception as e:
        return f"(could not read error queue: {e})"
    return "scope errors: " + " | ".join(errs) if errs else "no scope errors"


def register(mcp, conn):
    @mcp.tool()
    def scpi_query(command: str) -> str:
        """Send a SCPI query (must end in '?') and return the text reply.
        Not for binary data (screenshots, raw waveforms)."""
        if not conn.connected:
            return "Not connected. Call connect() first."
        problem = safety.check_query(command)
        if problem:
            return problem
        try:
            return conn.query(command)
        except Exception as e:
            return f"Query failed: {e}\n{_error_note(conn)}"

    @mcp.tool()
    def scpi_write(command: str, confirmed: bool = False) -> str:
        """Send a SCPI command that changes scope settings, then report the scope's error
        queue so you can fix bad syntax. Disruptive commands (*RST, *RCL, *SAV, presets)
        are refused unless confirmed=True, and only set that after the user agrees."""
        if not conn.connected:
            return "Not connected. Call connect() first."
        problem = safety.check_write(command, confirmed)
        if problem:
            return problem
        try:
            conn.write(command)
        except Exception as e:
            return f"Write failed: {e}"
        return f"sent; {_error_note(conn)}"
