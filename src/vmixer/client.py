"""Exclusive V-Mixer client over Serial or Telnet transport."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .commands import (
    AuxSend,
    ch_token,
    aux_token,
    normalize_pan_for_set,
    parse_axs,
    parse_cns,
)
from .protocol import (
    ACK,
    FrameDecoder,
    ParsedMessage,
    ProtocolError,
    TelnetFrameDecoder,
    build_command,
    build_telnet_command,
    format_level,
    telnet_ack,
)
from .serial_transport import Transport

log = logging.getLogger(__name__)


class MixerClient:
    def __init__(self, transport: Transport, default_timeout: float = 1.0) -> None:
        self._t = transport
        self._timeout = default_timeout
        self._lock = threading.RLock()
        self._framing = getattr(transport, "framing", "serial")
        self._dec: FrameDecoder | TelnetFrameDecoder = self._new_decoder()

    def _new_decoder(self):
        if self._framing == "telnet":
            return TelnetFrameDecoder()
        return FrameDecoder()

    def _encode(self, opcode: str, *params: str) -> bytes:
        if self._framing == "telnet":
            return build_telnet_command(opcode, *params)
        return build_command(opcode, *params)

    def _encode_ack(self) -> bytes:
        if self._framing == "telnet":
            return telnet_ack()
        return bytes([ACK])

    def close(self) -> None:
        self._t.close()

    def _transact_until(
        self,
        request: bytes,
        accept,
        timeout: Optional[float] = None,
        send_ack_after_cmd: bool = False,
    ) -> ParsedMessage:
        timeout = self._timeout if timeout is None else timeout
        with self._lock:
            self._dec = self._new_decoder()
            while True:
                junk = self._t.read(0.01)
                if not junk:
                    break
            self._t.write(request)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                chunk = self._t.read(min(0.05, max(0.0, deadline - time.monotonic())))
                if not chunk:
                    continue
                for msg in self._dec.feed(chunk):
                    if msg.kind == "err":
                        raise ProtocolError(f"mixer ERR:{msg.err_code}")
                    if accept(msg):
                        if send_ack_after_cmd and msg.kind == "cmd":
                            self._t.write(self._encode_ack())
                        return msg
            raise TimeoutError(f"timeout waiting reply for {request!r}")

    def version(self) -> str:
        msg = self._transact_until(
            self._encode("VRQ"),
            lambda m: m.kind == "cmd" and m.opcode in ("VRS", "VRQ"),
            send_ack_after_cmd=True,
        )
        return ",".join(msg.params) if msg.params else msg.opcode

    def query_aux(self, channel: int, aux: int) -> AuxSend:
        msg = self._transact_until(
            self._encode("AXQ", ch_token(channel), aux_token(aux)),
            lambda m: m.kind == "cmd" and m.opcode == "AXS",
            send_ack_after_cmd=True,
        )
        return parse_axs(msg)

    def set_aux(
        self, channel: int, aux: int, level_db: float | str, pan: str = "C"
    ) -> None:
        self._transact_until(
            self._encode(
                "AXC",
                ch_token(channel),
                aux_token(aux),
                format_level(level_db),
                normalize_pan_for_set(pan),
            ),
            lambda m: m.kind == "ack",
        )

    def query_name(self, channel: int) -> str:
        return self.query_name_token(ch_token(channel))

    def query_aux_name(self, aux: int) -> str:
        return self.query_name_token(aux_token(aux))

    def query_name_token(self, token: str) -> str:
        msg = self._transact_until(
            self._encode("CNQ", token),
            lambda m: m.kind == "cmd" and m.opcode == "CNS",
            send_ack_after_cmd=True,
        )
        _kind, _n, name = parse_cns(msg)
        return name
