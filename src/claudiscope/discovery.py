"""Finding the scope: saved address first, then whatever VISA can see."""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".claudiscope.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_last_resource(resource):
    cfg = load_config()
    cfg["last_resource"] = resource
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass  # not being able to save config is never fatal


def candidates(conn):
    """Resource strings to try, best first. Serial ports are skipped (probing can hang)."""
    found = []
    last = load_config().get("last_resource")
    if last:
        found.append(last)
    try:
        for r in conn.list_resources():
            if r not in found and not r.upper().startswith("ASRL"):
                found.append(r)
    except Exception:
        pass
    return found


def auto_connect(conn):
    """Try each candidate until one answers *IDN?. Returns the IDN string."""
    tried = candidates(conn)
    if not tried:
        raise RuntimeError(
            "No saved address and VISA sees no instruments. LAN scopes often don't "
            "appear in scans: pass the address, e.g. TCPIP0::192.168.137.1::INSTR"
        )
    failures = []
    for resource in tried:
        try:
            idn = conn.connect(resource, timeout_ms=3000)
            conn.inst.timeout = 10000
            save_last_resource(resource)
            return idn
        except Exception as e:
            failures.append(f"{resource}: {e}")
            conn.close()
    raise RuntimeError("Could not connect to any candidate. " + " | ".join(failures))
