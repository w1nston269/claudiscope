"""Entry point for the `claudiscope` command."""

import argparse
import sys

from claudiscope import __version__
from claudiscope.discovery import load_config


def _doctor():
    print(f"claudiscope {__version__}, Python {sys.version.split()[0]}")
    try:
        from importlib.metadata import version
        print("mcp:", version("mcp"))
    except Exception as e:
        print("mcp: MISSING", e)
    try:
        import pyvisa
    except ImportError:
        print("pyvisa: MISSING (pip install pyvisa)")
        return 1
    print("pyvisa:", pyvisa.__version__)
    try:
        rm = pyvisa.ResourceManager()
        print("VISA backend:", rm.visalib)
        found = rm.list_resources()
        print("VISA resources:", list(found) or "none (normal for LAN-only scopes)")
    except Exception as e:
        print("VISA backend: NOT FOUND -", e)
        print("Install R&S VISA or NI-VISA, or use pyvisa-py.")
    print("Saved address:", load_config().get("last_resource", "none"))
    return 0


def _scan():
    from claudiscope.connection import ScopeConnection
    from claudiscope.discovery import auto_connect
    conn = ScopeConnection()
    try:
        idn = auto_connect(conn)
        print(f"Found {conn.resource}: {idn}")
        conn.close()
        return 0
    except Exception as e:
        print(e)
        return 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="claudiscope", description="Let Claude drive a SCPI oscilloscope.")
    p.add_argument("--version", action="version", version=f"claudiscope {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the MCP server (tool mode)")
    sh = sub.add_parser("shell", help="interactive SCPI prompt (text mode)")
    sh.add_argument("-r", "--resource", help="e.g. TCPIP0::192.168.137.1::INSTR")
    sub.add_parser("scan", help="find and identify the scope")
    sub.add_parser("doctor", help="check the install")
    up = sub.add_parser("update", help="update claudiscope to the latest version")
    up.add_argument("--check", action="store_true", help="only check whether an update is available")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        from claudiscope.server import serve
        serve()
        return 0
    if args.cmd == "shell":
        from claudiscope.shell import run
        return run(args.resource)
    if args.cmd == "scan":
        return _scan()
    if args.cmd == "update":
        from claudiscope.update import run
        return run(check_only=args.check)
    return _doctor()


if __name__ == "__main__":
    sys.exit(main())