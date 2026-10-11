"""Serial / fake transports with exclusive access."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod

from .protocol import ACK, FrameDecoder, ParsedMessage, STX

log = logging.getLogger(__name__)


class Transport(ABC):
    framing: str = "serial"

    @abstractmethod
    def write(self, data: bytes) -> None: ...

    @abstractmethod
    def read(self, timeout: float) -> bytes: ...

    @abstractmethod
    def close(self) -> None: ...


class SerialTransport(Transport):
    framing = "serial"

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.05,
    ) -> None:
        import serial  # lazy

        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,
            timeout=timeout,
        )

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def read(self, timeout: float) -> bytes:
        self._ser.timeout = timeout
        n = self._ser.in_waiting
        if n:
            return self._ser.read(n)
        return self._ser.read(1)

    def close(self) -> None:
        self._ser.close()


class FakeTransport(Transport):
    """In-memory mixer: stores AUX matrix and answers AXQ/AXC/VRQ/CNQ."""

    framing = "serial"

    def __init__(self) -> None:
        self._tx = bytearray()
        self._lock = threading.Lock()
        self.levels = {
            (c, a): float("-inf") for c in range(1, 33) for a in range(1, 9)
        }
        self.pans = {(c, a): "C" for c in range(1, 33) for a in range(1, 9)}
        self.names = {c: f"CH{c:02d}" for c in range(1, 33)}
        self.aux_names = {a: f"AUX{a}"[:6] for a in range(1, 9)}
        self._dec = FrameDecoder()
        self.levels[(1, 1)] = -6.5
        self.levels[(2, 1)] = 0.0
        self.levels[(3, 1)] = -12.0

    def write(self, data: bytes) -> None:
        with self._lock:
            for msg in self._dec.feed(data):
                self._handle(msg)

    def _handle(self, msg: ParsedMessage) -> None:
        if msg.kind != "cmd":
            return
        if msg.opcode == "VRQ":
            self._reply(b"\x02VRS:M-200i,FAKE;")
            return
        if msg.opcode == "AXQ" and len(msg.params) >= 2:
            from .commands import parse_aux_token, parse_ch_token
            from .protocol import format_level

            ch = parse_ch_token(msg.params[0])
            aux = parse_aux_token(msg.params[1])
            lv = self.levels[(ch, aux)]
            pan = self.pans[(ch, aux)]
            lv_s = "INF" if lv == float("-inf") else format_level(lv)
            body = f"AXS:{msg.params[0]},{msg.params[1]},{lv_s},{pan}"
            self._reply(bytes([STX]) + body.encode() + b";")
            return
        if msg.opcode == "AXC" and len(msg.params) >= 4:
            from .commands import parse_aux_token, parse_ch_token
            from .protocol import parse_level

            ch = parse_ch_token(msg.params[0])
            aux = parse_aux_token(msg.params[1])
            self.levels[(ch, aux)] = parse_level(msg.params[2])
            self.pans[(ch, aux)] = msg.params[3]
            self._reply(bytes([ACK]))
            return
        if msg.opcode == "CNQ" and msg.params:
            tok = msg.params[0]
            if tok.startswith("AX"):
                from .commands import parse_aux_token

                aux = parse_aux_token(tok)
                name = self.aux_names.get(aux, f"AUX{aux}"[:6])
                body = f'CNS:{tok},"{name}"'
                self._reply(bytes([STX]) + body.encode() + b";")
                return
            from .commands import parse_ch_token

            ch = parse_ch_token(tok)
            name = self.names.get(ch, "      ")
            body = f'CNS:{tok},"{name}"'
            self._reply(bytes([STX]) + body.encode() + b";")
            return
        self._reply(b"\x02ERR:5;")

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
