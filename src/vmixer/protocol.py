"""V-Mixer RS-232C / Telnet framing and parsing (PDF v2.2 + Telnet Reference)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STX = 0x02
ACK = 0x06
XON = 0x11
XOFF = 0x13


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class ParsedMessage:
    kind: str  # "ack" | "err" | "cmd"
    opcode: str = ""
    params: tuple[str, ...] = ()
    err_code: Optional[int] = None
    raw: bytes = b""


def build_body(opcode: str, *params: str) -> str:
    if len(opcode) != 3 or not opcode.isalpha() or not opcode.isupper():
        raise ProtocolError(f"invalid opcode: {opcode!r}")
    body = opcode
    if params:
        body += ":" + ",".join(params)
    return body + ";"


def build_command(opcode: str, *params: str) -> bytes:
    """RS-232C: stx + body."""
    return bytes([STX]) + build_body(opcode, *params).encode("ascii")


def build_telnet_command(opcode: str, *params: str) -> bytes:
    """Telnet: body without stx, terminated with CR-LF."""
    return build_body(opcode, *params).encode("ascii") + b"\r\n"


def telnet_ack() -> bytes:
    return b"OK\r\n"


def format_level(level: float | str) -> str:
    if isinstance(level, str):
        if level.upper() == "INF":
            return "INF"
        level = float(level)
    if level == float("-inf") or level <= -80.0:
        return "INF"
    return f"{level:.1f}"


def parse_level(token: str) -> float:
    if token.upper() == "INF":
        return float("-inf")
    return float(token)


def _parse_text_payload(text: str, raw: bytes) -> ParsedMessage:
    text = text.strip()
    if text.upper() == "OK":
        return ParsedMessage(kind="ack", raw=raw)
    if text.upper() == "QUIT":
        return ParsedMessage(kind="cmd", opcode="BYE", params=(), raw=raw)
    if text.startswith("ERR:"):
        code_s = text[4:]
        try:
            code = int(code_s.strip().rstrip(";"))
        except ValueError as e:
            raise ProtocolError(f"bad ERR: {text}") from e
        return ParsedMessage(kind="err", opcode="ERR", err_code=code, raw=raw)
    if text.endswith(";"):
        text = text[:-1]
    if ":" in text:
        opcode, rest = text.split(":", 1)
        params = tuple(rest.split(","))
    else:
        opcode = text
        params = ()
    if len(opcode) != 3:
        raise ProtocolError(f"bad opcode in {text!r}")
    return ParsedMessage(kind="cmd", opcode=opcode.upper(), params=params, raw=raw)


class FrameDecoder:
    """Incremental decoder for RS-232C ack and stx...; frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[ParsedMessage]:
        out: list[ParsedMessage] = []
        for b in data:
            if b in (XON, XOFF):
                continue
            if b == ACK and not self._buf:
                out.append(ParsedMessage(kind="ack", raw=bytes([ACK])))
                continue
            if not self._buf:
                if b == STX:
                    self._buf.append(b)
                continue
            self._buf.append(b)
            if b == ord(";"):
                raw = bytes(self._buf)
                self._buf.clear()
                out.append(self._parse_frame(raw))
        return out

    def _parse_frame(self, raw: bytes) -> ParsedMessage:
        if not raw.startswith(bytes([STX])) or not raw.endswith(b";"):
            raise ProtocolError(f"bad frame: {raw!r}")
        return _parse_text_payload(raw[1:-1].decode("ascii", errors="replace") + ";", raw)


class TelnetFrameDecoder:
    """Line-oriented decoder: no stx; ack is the text OK (Telnet Reference)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[ParsedMessage]:
        out: list[ParsedMessage] = []
        for b in data:
            if b == ord("\r"):
                continue
            if b == ord("\n"):
                if self._buf:
                    raw = bytes(self._buf)
                    self._buf.clear()
                    out.append(
                        _parse_text_payload(raw.decode("ascii", errors="replace"), raw)
                    )
                continue
            self._buf.append(b)
            if b == ord(";") and self._buf:
                raw = bytes(self._buf)
                self._buf.clear()
                out.append(
                    _parse_text_payload(raw.decode("ascii", errors="replace"), raw)
                )
        return out
