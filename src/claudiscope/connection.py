"""VISA connection wrapper shared by the MCP server and the shell."""

import pyvisa

MAX_REPLY_CHARS = 20000


class ScopeConnection:
    def __init__(self):
        self._rm = None
        self.inst = None
        self.resource = None
        self.idn = None

    def _resource_manager(self, backend=None):
        # backend="@py" selects the pure-Python pyvisa-py backend
        if self._rm is None:
            self._rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
        return self._rm

    def list_resources(self, backend=None):
        return list(self._resource_manager(backend).list_resources())

    def connect(self, resource, timeout_ms=10000, backend=None):
        """Open a resource, e.g. 'TCPIP0::192.168.137.1::INSTR'. Returns the *IDN? reply."""
        self.close()
        rm = self._resource_manager(backend)
        self.inst = rm.open_resource(resource)
        self.inst.timeout = timeout_ms
        self.resource = resource
        self.idn = self.inst.query("*IDN?").strip()
        return self.idn

    @property
    def connected(self):
        return self.inst is not None

    def _require(self):
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")

    def query(self, command):
        self._require()
        reply = self.inst.query(command).strip()
        if len(reply) > MAX_REPLY_CHARS:
            reply = reply[:MAX_REPLY_CHARS] + f"\n...[truncated, {len(reply)} chars total]"
        return reply

    def write(self, command):
        self._require()
        self.inst.write(command)

    def read_binary(self, command):
        """Send a command and return the raw bytes of an IEEE 488.2 block reply."""
        self._require()
        return bytes(self.inst.query_binary_values(command, datatype="B", container=bytes))

    def errors(self, limit=10):
        """Drain the SCPI error queue. Returns a list of error strings (empty if clean)."""
        self._require()
        found = []
        for _ in range(limit):
            reply = self.inst.query("SYSTem:ERRor?").strip()
            if reply.startswith("0,") or reply.startswith("+0,"):
                break
            found.append(reply)
        return found

    def close(self):
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
        self.inst = None
        self.resource = None
        self.idn = None
