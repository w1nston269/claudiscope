"""Finding the scope, cheapest first:

1. the address that worked last time, and anything VISA lists by itself
2. a LAN sweep: ARP-table neighbours plus every local subnet, looking for the SCPI
   raw-socket port (5025) and the VXI-11 portmapper (111), then confirming with *IDN?

Only the standard library is used (psutil is picked up if it happens to be installed).
"""

import ipaddress
import json
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONFIG_PATH = Path.home() / ".claudiscope.json"

SCPI_PORTS = (5025, 111)   # raw SCPI socket, VXI-11 portmapper
PORT_TIMEOUT = 0.4         # seconds per TCP probe
MAX_SWEEP_HOSTS = 2048
_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"


# ---------------------------------------------------------------- config

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


# ---------------------------------------------------------------- helpers

def _short(exc, limit=140):
    text = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _run(cmd):
    """Run a command and return its stdout, or '' if it isn't available."""
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: no console flash
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=5, **kwargs)
        return r.stdout
    except Exception:
        return ""


def _is_mask(token):
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{token}")
        return token != "0.0.0.0"
    except ValueError:
        return False


def _iface(address, mask):
    try:
        return ipaddress.IPv4Interface(f"{address}/{mask}")
    except ValueError:
        return None


def _ip_of(resource):
    m = re.match(r"TCPIP\d*::([^:]+)::", resource or "", re.I)
    return m.group(1) if m else None


# ---------------------------------------------------------------- local network

def _parse_ipconfig(text):
    """Pair each IPv4 address with the subnet mask that follows it (locale independent)."""
    found, last = [], None
    for token in re.findall(_IPV4, text):
        if _is_mask(token):
            if last:
                found.append(_iface(last, token))
                last = None
        else:
            last = token
    return [i for i in found if i]


def _parse_ip_addr(text):
    found = []
    for cidr in re.findall(rf"inet ({_IPV4}/\d+)", text):
        try:
            found.append(ipaddress.IPv4Interface(cidr))
        except ValueError:
            pass
    return found


def _parse_ifconfig(text):
    found = []
    for addr, mask in re.findall(rf"inet (?:addr:)?({_IPV4})\s+(?:netmask|Mask:)\s*(\S+)", text):
        if mask.lower().startswith("0x"):
            try:
                mask = str(ipaddress.IPv4Address(int(mask, 16)))
            except ValueError:
                continue
        iface = _iface(addr, mask)
        if iface:
            found.append(iface)
    return found


def local_interfaces():
    """IPv4 addresses (with masks) of every network interface on this computer."""
    found = []
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET and a.address and a.netmask:
                    iface = _iface(a.address, a.netmask)
                    if iface:
                        found.append(iface)
    except Exception:
        pass
    if not found:
        if sys.platform.startswith("win"):
            found = _parse_ipconfig(_run(["ipconfig"]))
        else:
            found = (_parse_ip_addr(_run(["ip", "-4", "-o", "addr", "show"]))
                     or _parse_ifconfig(_run(["ifconfig"])))
    unique = list(dict.fromkeys(found))
    return [i for i in unique if not i.ip.is_loopback and i.network.prefixlen < 32]


def arp_neighbors():
    """IPv4 addresses this computer has recently talked to on the LAN."""
    text = _run(["arp", "-a"]) or _run(["ip", "neigh"])
    ips = set()
    for line in text.splitlines():
        if not re.search(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", line):
            continue
        if "ff:ff:ff:ff:ff:ff" in line.lower().replace("-", ":"):
            continue
        m = re.search(_IPV4, line)
        if not m:
            continue
        try:
            ip = ipaddress.IPv4Address(m.group())
        except ValueError:
            continue
        if not (ip.is_multicast or ip.is_loopback or ip == ipaddress.IPv4Address("255.255.255.255")):
            ips.add(str(ip))
    return ips


# ---------------------------------------------------------------- probing

def _port_open(ip, port, timeout=PORT_TIMEOUT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def _raw_idn(ip, port=5025, timeout=1.5):
    """Ask a raw SCPI socket for *IDN?. Returns the reply text or None."""
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"*IDN?\n")
            data = b""
            while not data.endswith(b"\n") and len(data) < 512:
                chunk = s.recv(256)
                if not chunk:
                    break
                data += chunk
            return data.decode(errors="replace").strip() or None
    except OSError:
        return None


def scan_network(notes):
    """Sweep the LAN. Returns (raw_socket_hits, portmapper_hosts).

    raw_socket_hits: [(ip, idn_reply)] for hosts that answered *IDN? on port 5025.
    portmapper_hosts: [ip] with port 111 open (candidates for a VXI-11 instrument).
    """
    ifaces = local_interfaces()
    if not ifaces:
        notes.append("Could not work out this computer's network addresses, so the LAN sweep was skipped.")
        return [], []
    own = {str(i.ip) for i in ifaces}
    targets = {ip for ip in arp_neighbors() if ip not in own}
    from_arp = len(targets)

    subnets = []
    for i in ifaces:
        net = i.network if i.network.prefixlen >= 24 else ipaddress.ip_network(f"{i.ip}/24", strict=False)
        if net not in subnets:
            subnets.append(net)
    # the Windows Internet Connection Sharing range first: that's where a direct-cabled scope lives
    subnets.sort(key=lambda n: (not str(n.network_address).startswith("192.168.137."), str(n)))

    swept = []
    for net in subnets:
        hosts = [str(h) for h in net.hosts() if str(h) not in own]
        if len(targets) + len(hosts) > MAX_SWEEP_HOSTS:
            break
        targets.update(hosts)
        swept.append(str(net))
    notes.append(f"Checked {len(targets)} address(es): {from_arp} from the ARP table"
                 + (f", plus subnets {', '.join(swept)}." if swept else "."))

    def check(ip):
        return ip, [p for p in SCPI_PORTS if _port_open(ip, p)]

    ordered = sorted(targets, key=ipaddress.IPv4Address)
    with ThreadPoolExecutor(max_workers=96) as pool:
        results = list(pool.map(check, ordered))

    raw, portmap = [], []
    for ip, ports in results:
        if 5025 in ports:
            idn = _raw_idn(ip)
            if idn and "," in idn:
                raw.append((ip, idn))
                continue
        if 111 in ports:
            portmap.append(ip)
    return raw, portmap


# ---------------------------------------------------------------- discovery

def candidates(conn, notes=None):
    """Saved address first, then whatever VISA lists. Serial ports are skipped (probing can hang)."""
    found = []
    last = load_config().get("last_resource")
    if last:
        found.append(last)
    try:
        for r in conn.list_resources():
            if r not in found and not r.upper().startswith("ASRL"):
                found.append(r)
    except Exception as e:
        if notes is not None:
            notes.append(f"VISA could not list instruments: {_short(e)}")
    return found


def discover(conn, sweep="auto"):
    """Find scopes. Returns (found, notes); found is [{'resource', 'idn'}].

    sweep: 'auto' sweeps the LAN only if nothing was found yet, 'always', or 'never'.
    """
    found, notes, seen_ips = [], [], set()
    visa_error = None

    def add(resource, idn):
        if all(f["resource"] != resource for f in found):
            found.append({"resource": resource, "idn": idn})

    if conn.connected:
        add(conn.resource, conn.idn)  # don't reopen a session we already hold
        ip = _ip_of(conn.resource)
        if ip:
            seen_ips.add(ip)

    for res in candidates(conn, notes):
        if res == conn.resource:
            continue
        ip = _ip_of(res)
        if ip and not any(_port_open(ip, p, 0.6) for p in SCPI_PORTS):
            notes.append(f"{res}: nothing is answering at {ip} (the address may have changed).")
            continue
        try:
            add(res, conn.probe(res))
            if ip:
                seen_ips.add(ip)
        except Exception as e:
            visa_error = visa_error or e
            notes.append(f"{res}: {_short(e)}")

    if sweep == "always" or (sweep == "auto" and not found):
        raw, portmap = scan_network(notes)
        for ip, raw_idn in raw:
            if ip in seen_ips:
                continue
            for res in (f"TCPIP0::{ip}::INSTR", f"TCPIP0::{ip}::5025::SOCKET"):
                try:
                    add(res, conn.probe(res))
                    break
                except Exception as e:
                    visa_error = visa_error or e
            else:
                add(f"TCPIP0::{ip}::5025::SOCKET", raw_idn)
                notes.append(f"{ip} answered *IDN? on port 5025, but VISA couldn't open it: {_short(visa_error)}")
        for ip in portmap[:8]:
            if ip in seen_ips:
                continue
            res = f"TCPIP0::{ip}::INSTR"
            try:
                add(res, conn.probe(res))
            except Exception as e:  # plenty of non-instruments run a portmapper
                visa_error = visa_error or e
        if len(portmap) > 8:
            notes.append(f"{len(portmap)} hosts had port 111 open; only the first 8 were tried with VISA.")
        if not found:
            notes.append("No device answered on the SCPI ports (5025 or 111). "
                         "Is the scope on, on this network, and its LAN interface enabled?")
            if visa_error:
                notes.append(f"VISA reported: {_short(visa_error)}")

    return found, list(dict.fromkeys(notes))


def format_report(found, notes):
    lines = ([f"Found {len(found)} instrument(s):"] + [f"  {f['resource']}  {f['idn']}" for f in found]
             if found else ["No instruments found."])
    if notes:
        lines += ["", "Notes:"] + [f"  - {n}" for n in notes]
    return "\n".join(lines)


def auto_connect(conn):
    """Connect to the best instrument discover() finds. Returns the *IDN? reply."""
    found, notes = discover(conn, sweep="auto")
    if not found:
        raise RuntimeError(format_report(found, notes)
                           + "\nIf you know the address, pass it: TCPIP0::<ip>::INSTR")
    found.sort(key=lambda f: "rohde" not in f["idn"].lower())
    best = found[0]
    if conn.connected and conn.resource == best["resource"]:
        return conn.idn
    idn = conn.connect(best["resource"])
    save_last_resource(best["resource"])
    return idn