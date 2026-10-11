"""TCP Telnet transport for M-200i (LAN, port 8023)."""

from __future__ import annotations

import logging
import socket
import threading
import time

from .protocol import (
    TelnetFrameDecoder,
    format_level,
    telnet_ack,
)
from .serial_transport import Transport

log = logging.getLogger(__name__)

DEFAULT_TELNET_PORT = 8023


class TelnetTransport(Transport):
    """Raw TCP to M-200i Telnet server (not a full Telnet option negotiator)."""

    framing = "telnet"

    def __init__(self, host: str, port: int = DEFAULT_TELNET_PORT, timeout: float = 2.0) -> None:
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(0.05)
        self._lock = threading.Lock()
        log.info("telnet connected to %s:%s", host, port)

    def write(self, data: bytes) -> None:
        with self._lock:
            self._sock.sendall(data)

    def read(self, timeout: float) -> bytes:
        self._sock.settimeout(max(timeout, 0.001))
        try:
            chunk = self._sock.recv(4096)
            return chunk or b""
        except socket.timeout:
            return b""
        except OSError:
            return b""

    def close(self) -> None:
        try:
            with self._lock:
                try:
                    self._sock.sendall(b"QUIT\r\n")
                except OSError:
                    pass
                self._sock.close()
        except OSError:
            pass


class FakeTelnetTransport(Transport):
    """In-memory mixer speaking Telnet dialect (no stx; OK instead of ack)."""

    framing = "telnet"

    def __init__(self) -> None:
        self._tx = bytearray()
        self._lock = threading.Lock()
        self.levels = {
            (c, a): float("-inf") for c in range(1, 33) for a in range(1, 9)
        }
        self.pans = {(c, a): "C" for c in range(1, 33) for a in range(1, 9)}
        self.names = {c: f"CH{c:02d}" for c in range(1, 33)}
        self.aux_names = {a: f"MON{a}"[:6] for a in range(1, 9)}
        self._dec = TelnetFrameDecoder()
        self.levels[(1, 1)] = -6.5
        self.levels[(2, 1)] = 0.0
        self.levels[(3, 1)] = -12.0

    def write(self, data: bytes) -> None:
        with self._lock:
            for msg in self._dec.feed(data):
                self._handle(msg)

    def _handle(self, msg) -> None:
        if msg.kind == "ack":
            # client OK after our reply — ignore
            return
        if msg.kind != "cmd":
            return
        if msg.opcode == "VRQ":
            self._reply(b"VRS:M-200i,FAKE-TELNET;\r\n")
            return
        if msg.opcode == "AXQ" and len(msg.params) >= 2:
            from .commands import parse_aux_token, parse_ch_token

            ch = parse_ch_token(msg.params[0])
            aux = parse_aux_token(msg.params[1])
            lv = self.levels[(ch, aux)]
            pan = self.pans[(ch, aux)]
            lv_s = "INF" if lv == float("-inf") else format_level(lv)
            body = f"AXS:{msg.params[0]},{msg.params[1]},{lv_s},{pan};\r\n"
            self._reply(body.encode())
            return
        if msg.opcode == "AXC" and len(msg.params) >= 4:
            from .commands import parse_aux_token, parse_ch_token
            from .protocol import parse_level

            ch = parse_ch_token(msg.params[0])
            aux = parse_aux_token(msg.params[1])
            self.levels[(ch, aux)] = parse_level(msg.params[2])
            self.pans[(ch, aux)] = msg.params[3]
            self._reply(telnet_ack())
            return
        if msg.opcode == "CNQ" and msg.params:
            tok = msg.params[0]
            if tok.startswith("AX"):
                from .commands import parse_aux_token

                aux = parse_aux_token(tok)
                name = self.aux_names.get(aux, f"AUX{aux}"[:6])
                self._reply(f'CNS:{tok},"{name}";\r\n'.encode())
                return
            from .commands import parse_ch_token

            ch = parse_ch_token(tok)
            name = self.names.get(ch, "      ")
            self._reply(f'CNS:{tok},"{name}";\r\n'.encode())
            return
        if msg.opcode == "BYE":
            return
        self._reply(b"ERR:5;\r\n")

    def _reply(self, data: bytes) -> None:
        self._tx.extend(data)

    def read(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._tx:
                    out = bytes(self._tx)
                    self._tx.clear()
                    return out
            time.sleep(0.001)
        return b""

    def close(self) -> None:
        pass


# silence unused import warning if any
