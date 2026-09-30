"""Text mode: a SCPI REPL for you at the keyboard."""

from claudiscope import safety
from claudiscope.connection import ScopeConnection
from claudiscope.discovery import auto_connect, save_last_resource


def run(resource=None):
    conn = ScopeConnection()
    try:
        if resource:
            idn = conn.connect(resource)
            save_last_resource(resource)
        else:
            idn = auto_connect(conn)
    except Exception as e:
        print(f"Could not connect: {e}")
        return 1
    print(f"Connected to {conn.resource}\n{idn}\nType SCPI commands. 'quit' to exit.")
    while True:
        try:
            cmd = input("scpi> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd.lower() in ("quit", "exit"):
            break
        try:
            if cmd.endswith("?"):
                print(conn.query(cmd))
                continue
            level, part = safety.classify(cmd)
            if level and input(f"'{part}' is a {level}-tier command. Send anyway? [y/N] ").lower() != "y":
                continue
            conn.write(cmd)
            errs = conn.errors()
            print("sent" + (f"; scope errors: {errs}" if errs else ""))
        except Exception as e:
            print(f"error: {e}")
    conn.close()
    return 0
