"""M-200i AUX command helpers (AXQ/AXS/AXC, VRQ, CNQ)."""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import ParsedMessage, ProtocolError, build_command, format_level, parse_level

MAX_INPUT = 32
MAX_AUX = 8


def ch_token(ch: int) -> str:
    if not 1 <= ch <= MAX_INPUT:
        raise ProtocolError(f"channel out of range: {ch}")
    return f"I{ch}"


def aux_token(aux: int) -> str:
    if not 1 <= aux <= MAX_AUX:
        raise ProtocolError(f"aux out of range: {aux}")
    return f"AX{aux}"


def parse_ch_token(tok: str) -> int:
    if not tok.startswith("I"):
        raise ProtocolError(f"not an input channel: {tok}")
    return int(tok[1:])


def parse_aux_token(tok: str) -> int:
    if not tok.startswith("AX"):
        raise ProtocolError(f"not an AUX: {tok}")
    return int(tok[2:])


def parse_name_target(tok: str) -> tuple[str, int]:
    """Return ('I'|'AX', n) for CNQ/CNS targets."""
    if tok.startswith("AX"):
        n = int(tok[2:])
        if not 1 <= n <= MAX_AUX:
            raise ProtocolError(f"aux out of range: {tok}")
        return "AX", n
    if tok.startswith("I"):
        n = int(tok[1:])
        if not 1 <= n <= MAX_INPUT:
            raise ProtocolError(f"channel out of range: {tok}")
        return "I", n
    raise ProtocolError(f"unsupported name target: {tok}")


@dataclass(frozen=True)
class AuxSend:
    channel: int
    aux: int
    level_db: float
    pan: str  # L63..C..R63; AXS returns "0" when AUX is not stereo-linked


def normalize_pan_for_set(pan: str) -> str:
    """AXC requires L63–C–R63; mono AUX queries return pan '0' which is invalid on set."""
    p = (pan or "").strip().upper()
    if not p or p == "0":
        return "C"
    if p == "C":
        return "C"
    if (p.startswith("L") or p.startswith("R")) and p[1:].isdigit():
        n = int(p[1:])
        if 0 <= n <= 63:
            return f"{p[0]}{n}"
    return "C"


def cmd_vrq() -> bytes:
    return build_command("VRQ")


def cmd_axq(channel: int, aux: int) -> bytes:
    return build_command("AXQ", ch_token(channel), aux_token(aux))


def cmd_axc(channel: int, aux: int, level_db: float | str, pan: str = "C") -> bytes:
    return build_command(
        "AXC",
        ch_token(channel),
        aux_token(aux),
        format_level(level_db),
        normalize_pan_for_set(pan),
    )


def cmd_cnq(channel: int) -> bytes:
    return build_command("CNQ", ch_token(channel))


def cmd_cnq_target(token: str) -> bytes:
    return build_command("CNQ", token)


def parse_axs(msg: ParsedMessage) -> AuxSend:
    if msg.kind != "cmd" or msg.opcode != "AXS" or len(msg.params) < 4:
        raise ProtocolError(f"not AXS: {msg}")
    return AuxSend(
        channel=parse_ch_token(msg.params[0]),
        aux=parse_aux_token(msg.params[1]),
        level_db=parse_level(msg.params[2]),
        pan=msg.params[3],
    )


def parse_cns(msg: ParsedMessage) -> tuple[str, int, str]:
    """Return (kind, n, name) where kind is 'I' or 'AX'."""
    if msg.kind != "cmd" or msg.opcode != "CNS" or len(msg.params) < 2:
        raise ProtocolError(f"not CNS: {msg}")
    kind, n = parse_name_target(msg.params[0])
    name = ",".join(msg.params[1:]).strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1]
    else:
        name = name.strip('"')
    return kind, n, name.strip()
