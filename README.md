# claudiscope 🔬

**Give Claude a pair of probes.**

claudiscope is a small [MCP](https://modelcontextprotocol.io) server that lets Claude (or you!) talk to your oscilloscope over SCPI. Ask it to measure a signal, change the timebase, or take a screenshot, and it does the fiddling so you don't have to hunt through menus with a greasy thumb.

Built and tested on a **Rohde & Schwarz RTB2004**. It's a plain SCPI passthrough, so other SCPI scopes *should* work, but nobody has tried, and I'm not going to pretend otherwise.

> ⚠️ **Heads up:** Claude (and you via this software) can change your scope's settings. Don't hand it the keys while the scope is hooked up to something you'd cry about. Read the [safety section](#safety-because-we-both-know-how-this-goes) first.

---

## What you get

- **Tool mode:** `claudiscope serve` runs an MCP server, and Claude drives the scope from a normal chat.
- **Text mode:** `claudiscope shell` is a plain SCPI prompt for when you'd rather type the commands yourself.
- **Auto-detect:** it remembers the last address that worked and tries it first, then whatever VISA can see.
- **Guardrails:** file, firmware and power commands are blocked, and disruptive ones like `*RST` need your OK.

---

## Before you install anything

You need three things:

1. **Python 3.10+**
2. **A VISA library** so Python can talk to the hardware:
   - **Windows:** install [R&S VISA](https://www.rohde-schwarz.com) or NI-VISA. Either works. R&S VISA is the one this was tested with.
   - **Linux:** no installer needed. `pyvisa-py` (below) does the job.
3. **A way to reach the scope**, either Ethernet or USB (see [Connecting the scope](#connecting-the-scope)).

Claude Desktop (Windows/Mac) or Claude Code (anywhere) is needed to actually chat with it.

---

## Installing

### Windows

Clone or download this repo, open a terminal in the folder that contains `pyproject.toml`, and run:

```
python -m pip install -e .
python -m claudiscope doctor
```

`doctor` checks that everything is wired up. If it prints your VISA backend and no red flags, carry on.

Prefer `pipx`?

```
pipx install git+https://github.com/w1nston269/claudiscope
```

> **Microsoft Store Python users:** the `claudiscope` command often isn't on your PATH. Use `python -m claudiscope <command>` everywhere instead. It does exactly the same thing.

### Linux

Modern Debian/Ubuntu won't let you `pip install` into the system Python (the `externally-managed-environment` error), so use a virtual environment:

```
sudo apt install python3-venv     # only if the next line complains
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pyvisa-py psutil zeroconf
claudiscope doctor
```

You'll need to run `source .venv/bin/activate` in each new terminal before `claudiscope` works.

### Version gotcha

`mcp` is pinned below 2.0, because 2.x renamed `FastMCP` and broke the imports. If you ever see `No module named 'mcp.server.fastmcp'`, run:

```
python -m pip install "mcp<2"
```

---

## Connecting the scope

### Option A: Ethernet (the tested one)

This is the easy route because it skips USB driver drama entirely.

1. Plug the scope into your router or straight into your laptop.
2. Find its IP in the scope's network/LAN settings (menu names vary by firmware).
3. Check the laptop can reach it:
   ```
   ping <scope-ip>
   ```
4. Try the shell:
   ```
   claudiscope shell -r TCPIP0::<scope-ip>::INSTR
   ```
   You should see an `*IDN?` reply starting with `Rohde&Schwarz,RTB2004,...`.

**Direct cable, no router?** DHCP has nothing to hand out addresses, so either set static IPs on both ends in the same subnet (say scope `192.168.0.10`, laptop `192.168.0.11`, mask `255.255.255.0`), or on Windows use Internet Connection Sharing, which puts everything on `192.168.137.x`.

**Timeouts?** Try the raw socket form of the address instead (check your scope's manual for the port, 5025 is common):
```
TCPIP0::<scope-ip>::5025::SOCKET
```

LAN scopes often don't show up in scans. That's normal. Give it the address once and it remembers.

### Option B: USB

Use the scope's rear **USB device** port (usually Type B), not the front ports. Those are for memory sticks and will ignore you.

- **Windows:** with R&S VISA or NI-VISA installed, the drivers come along for the ride. The scope should show up under "USB Test and Measurement Devices" in Device Manager. Then run `claudiscope scan`.
- **Linux:** you'll need `pyusb`, `libusb`, and probably a udev rule so your user is allowed to open the device. This route is fiddlier and less tested, so Ethernet is the easier choice.
- Make sure the scope's USB device mode is set to test-and-measurement (USBTMC), not a virtual COM port. The menu wording varies.

A USB resource string looks like `USB0::0x0AAD::0x01D6::<serial>::INSTR`. Trust what `claudiscope scan` prints rather than my example.

---

## The commands

| Command | What it does |
|---|---|
| `claudiscope doctor` | Checks Python, the `mcp` and `pyvisa` versions, your VISA backend, visible instruments, and the saved address. Run this first when something's broken. |
| `claudiscope scan` | Tries the saved address, then anything VISA can see, and prints the first scope that answers `*IDN?`. |
| `claudiscope shell` | Interactive SCPI prompt. Add `-r <resource>` to pick an address, otherwise it auto-detects. Lines ending in `?` are queries, and everything else is a write followed by an error-queue check. `quit` exits. |
| `claudiscope serve` | Starts the MCP server. You don't normally run this yourself, since Claude launches it. Run it by hand only to check it starts (it sits there quietly, and that's correct). |

Everything above also works as `python -m claudiscope <command>`.

---

## Hooking it up to Claude

### Claude Desktop (Windows / Mac)

Open Settings → Developer → Edit Config and add:

```json
{
  "mcpServers": {
    "claudiscope": {
      "command": "C:\\full\\path\\to\\python.exe",
      "args": ["-m", "claudiscope", "serve"]
    }
  }
}
```

Get the real path from the terminal where `doctor` works:

```
python -c "import sys; print(sys.executable)"
```

Use the **full path** with doubled backslashes. Desktop launches servers with its own environment, and a bare `python` may find a different Python than the one you installed into. Then **fully quit** Claude Desktop from the system tray and reopen it.

Check Settings → Developer: claudiscope should say *running*. Start a **new chat** and look for the tools in the message box (the icon is under "Search and tools" or behind the "+", depending on your version). If in doubt, type "Connect to the scope."

### Claude Code

```
claude mcp add claudiscope -- python -m claudiscope serve
claude mcp list
```

On Linux, point at the virtualenv's Python so the server can see its packages:

```
claude mcp add claudiscope -- /path/to/claudiscope/.venv/bin/python -m claudiscope serve
```

---

## What Claude can do with it

| Tool | Purpose |
|---|---|
| `connect` | Connects (auto-detect, or pass an address) and returns the scope's `*IDN?`. |
| `status` | Am I connected, and to what? |
| `scan` | Lists candidate addresses. |
| `scpi_query` | Sends a SCPI query (must end in `?`). |
| `scpi_write` | Sends a SCPI command, then reports the scope's error queue so Claude can correct itself. |
| `get_screenshot` | Grabs the display as an image. **Best-effort:** the `HCOPy` commands are unverified for the RTB2004. If it fails, edit the two constants at the top of `src/claudiscope/tools/screenshot.py` using your scope's programming manual. |

Try: *"Connect to the scope, measure Vpp and frequency on channel 1, then take a screenshot."*

Claude knows a fair amount of SCPI from memory but can get vendor-specific syntax slightly wrong. The error queue usually lets it fix itself, and attaching your scope's programming manual to the chat helps a lot.

---

## Safety (because we both know how this goes)

Two tiers, applied to everything Claude sends:

- **Blocked:** anything under `MMEM` (file operations), firmware commands, reboot and shutdown. Claude will tell you to run these yourself in the shell.
- **Needs your OK:** `*RST`, `*RCL`, `*SAV`, and presets. They wipe your carefully dialed-in settings, so Claude has to ask first.

The list is a starting point, not gospel. Tighten it against your scope's manual in `src/claudiscope/safety.py`. And Claude Desktop asks before running tools by default, so think twice before clicking "always allow".

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Could not locate a VISA implementation` | No VISA library. Install R&S VISA / NI-VISA (Windows) or `pyvisa-py` (Linux). |
| `list_resources()` comes back empty | Normal for LAN scopes. Give it the address. For USB, check the cable, Device Manager and USBTMC mode. |
| `No module named claudiscope` in the Desktop log | Desktop launched a different Python. Use the full path in the config. |
| `No module named 'mcp.server.fastmcp'` | You have `mcp` 2.x. `python -m pip install "mcp<2"`. |
| Server "disconnected" in Desktop | Read `%APPDATA%\Claude\logs\mcp-server-claudiscope.log`. The last traceback names the culprit. |
| Timeouts | `ping` the scope. Check nothing else has a session open to it and the link hasn't dropped. |

---

## Project layout

```
src/claudiscope/
├── cli.py          # serve / shell / scan / doctor
├── connection.py   # VISA session, error queue, truncation of huge replies
├── safety.py       # blocked / confirm tiers
├── discovery.py    # saved address + VISA scan (config lives in ~/.claudiscope.json)
├── server.py       # builds the MCP server
├── shell.py        # the text-mode prompt
└── tools/          # one file per group of MCP tools
```

Each file in `tools/` exposes a `register(mcp, conn)` function, so adding a tool means adding a file.

---

## Status and honesty corner

- **Tested:** RTB2004 over Ethernet with R&S VISA on Windows.
- **Untested:** USB, other scopes, most of the Linux path, and the screenshot commands.
- **Not yet:** waveform capture (raw data would swamp Claude's context, so it needs a summarizing tool first).

PRs and bug reports welcome, especially "it works on my Rigol" and "it exploded on my Tektronix."

Not affiliated with Rohde & Schwarz or Anthropic. Provided as-is. If it factory-resets your scope at a bad moment, that's on both of us.

## License

MIT