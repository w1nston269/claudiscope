"""MCP tool mode. NOTE: stdio transport, so never print() to stdout in here or in tools."""

from mcp.server.fastmcp import FastMCP

from claudiscope.connection import ScopeConnection
from claudiscope.tools import connect, scpi, screenshot

INSTRUCTIONS = """\
You are connected to a SCPI oscilloscope through claudiscope (expected: a Rohde & Schwarz RTB2004; \
connect() returns the real *IDN? so trust that). Call connect() first.
- Use scpi_query for reads (end with '?') and scpi_write for changes. scpi_write reports the scope's \
error queue: if it shows errors, fix the syntax and retry rather than guessing.
- Commands are vendor-specific. If unsure of syntax, say so and ask the user for the programming manual.
- Use get_screenshot to see the display. Chat clients can't show the image to the user inline, so when the user asks for a screenshot or wants to see the scope, call it with open_viewer=True (it pops up on their screen) and tell them the saved file path. Use a short descriptive name argument. Don't request raw waveform data through scpi_query.
- *RST, *RCL, *SAV and presets wipe settings: ask the user before using confirmed=True. File, firmware \
and power commands are blocked entirely.
"""


def build_server():
    mcp = FastMCP("claudiscope", instructions=INSTRUCTIONS)
    conn = ScopeConnection()
    for module in (connect, scpi, screenshot):
        module.register(mcp, conn)
    return mcp


def serve():
    build_server().run()