"""Two-tier guardrails for raw SCPI passthrough.

BLOCKED: can destroy things that can't be recovered (files, firmware, power).
         Never sent by Claude; the user must run them manually (e.g. in the shell).
CONFIRM: recoverable but disruptive (resets, recalls, presets).
         Only sent when scpi_write is called with confirmed=True, which Claude
         should do only after the user has said yes.

Best-effort prefix matching: tighten against your scope's programming manual.
"""

import re

BLOCKED_PREFIXES = (
    "MMEM",                       # every mass-memory (file system) write
    "FIRM", "SYST:FIRM", "SYSTEM:FIRM",
    "SYST:REB", "SYSTEM:REB",     # reboot
    "SYST:SHUT", "SYSTEM:SHUT",   # shutdown
)

CONFIRM_PREFIXES = (
    "*RST",                       # reset to default settings
    "*RCL",                       # recall a saved setup
    "*SAV",                       # save a setup (overwrites the slot)
    "SYST:PRES", "SYSTEM:PRES",   # preset
)


def _parts(command):
    """Split compound commands on ';' and newlines so '...;*RST' can't sneak through."""
    return [p.strip().lstrip(":").upper() for p in re.split(r"[;\n]", command) if p.strip()]


def classify(command):
    """Return (level, part): level is 'blocked', 'confirm' or None."""
    level, found = None, None
    for part in _parts(command):
        if part.endswith("?"):
            continue  # query forms are read-only
        if part.startswith(BLOCKED_PREFIXES):
            return "blocked", part
        if part.startswith(CONFIRM_PREFIXES) and level is None:
            level, found = "confirm", part
    return level, found


def check_query(command):
    """Return an error string if the query isn't allowed, else None."""
    if not command.strip().endswith("?"):
        return "Queries must end with '?'. Use scpi_write for commands that change settings."
    level, part = classify(command)
    if level:
        return f"Refused: '{part}' is embedded in a query. Send it separately with scpi_write."
    return None


def check_write(command, confirmed=False):
    """Return an error string if the write isn't allowed, else None."""
    level, part = classify(command)
    if level == "blocked":
        return (f"Blocked: '{part}' is a restricted command (files/firmware/power). "
                "Ask the user to run it manually on the scope or with `claudiscope shell`.")
    if level == "confirm" and not confirmed:
        return (f"Needs confirmation: '{part}' is disruptive (it can wipe current settings). "
                "Ask the user if they want it. If they say yes, call scpi_write again "
                "with confirmed=True.")
    return None
