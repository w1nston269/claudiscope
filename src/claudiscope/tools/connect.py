"""Tools for connecting to the scope and checking connection state."""

import claudiscope
from claudiscope.discovery import auto_connect, candidates, save_last_resource


def register(mcp, conn):
    @mcp.tool()
    def connect(resource: str = "") -> str:
        """Connect to the oscilloscope and return its *IDN? reply (manufacturer, model,
        serial, firmware). Leave resource empty to auto-detect (tries the last used
        address, then any VISA instruments). Or pass e.g. 'TCPIP0::192.168.137.1::INSTR'."""
        try:
            if resource:
                idn = conn.connect(resource)
                save_last_resource(resource)
            else:
                idn = auto_connect(conn)
            return f"Connected to {conn.resource}: {idn}"
        except Exception as e:
            return f"Connection failed: {e}"

    @mcp.tool()
    def status() -> str:
        """Report whether a scope is connected and which one, plus the claudiscope version
        and the file it is running from (useful for checking which install is live)."""
        where = f"claudiscope {claudiscope.__version__} running from {claudiscope.__file__}"
        if conn.connected:
            return f"Connected to {conn.resource}: {conn.idn}\n{where}"
        return f"Not connected. Call connect().\n{where}"

    @mcp.tool()
    def scan() -> str:
        """List candidate scope addresses (saved address plus VISA-visible instruments)."""
        found = candidates(conn)
        return "\n".join(found) if found else "No candidates found."