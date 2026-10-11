"""Load vmixer settings from config.toml, with env-var overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

TRANSPORTS = ("fake", "fake-telnet", "telnet", "serial")

_APP_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    transport: str = "fake"
    telnet_host: str = "192.168.0.50"
    telnet_port: int = 8023
    serial_port: str = "/dev/ttyUSB0"
    baud: int = 115200
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    auxes: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)
    config_path: Optional[Path] = None


def config_path(explicit: Optional[str] = None) -> Optional[Path]:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("VMIXER_CONFIG")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / "config.toml")
    candidates.append(_APP_ROOT / "config.toml")
    for path in candidates:
        if path.is_file():
            return path
    return None


def save_path(settings: Optional[Settings] = None) -> Path:
    env = os.environ.get("VMIXER_CONFIG")
    if env:
        return Path(env)
    if settings and settings.config_path:
        return settings.config_path
    found = config_path()
    if found:
        return found
    return _APP_ROOT / "config.toml"


def save_settings(settings: Settings, path: Optional[Path] = None) -> Path:
    target = path or save_path(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    auxes = ", ".join(str(n) for n in settings.auxes)
    text = f"""# Configuração do app V-Mixer (Roland M-200i)
# Depois de editar: sudo systemctl restart vmixer

# Como falar com a mesa:
#   telnet      — IP na porta LAN da mesa (recomendado)
#   serial      — cabo RS-232C / USB-serial
#   fake        — teste sem mesa
#   fake-telnet — teste do dialecto LAN, sem mesa
transporte = "{settings.transport}"

[mesa]
# IP da M-200i (porta LAN, não REAC). Porta Telnet padrão: 8023
ip = "{settings.telnet_host}"
porta = {int(settings.telnet_port)}

[serial]
# Só usado se transporte = "serial"
dispositivo = "{settings.serial_port}"
baud = {int(settings.baud)}

[web]
# 0.0.0.0 = acessível na rede (celulares na mesma Wi-Fi)
endereco = "{settings.listen_host}"
porta = {int(settings.listen_port)}

[aux]
# Quais AUXes aparecem na tela (M-200i: 1–8)
numeros = [{auxes}]
"""
    target.write_text(text, encoding="utf-8")
    return target


def load_settings(
    path: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Settings:
    env = os.environ if environ is None else environ
    data: dict[str, Any] = {}
    found = config_path(path)
    if found:
        data = _read_toml(found)

    mesa = data.get("mesa") or {}
    serial = data.get("serial") or {}
    web = data.get("web") or {}
    aux = data.get("aux") or {}

    transport = str(
        env.get("VMIXER_TRANSPORT") or data.get("transporte") or "fake"
    ).lower()
    if transport not in TRANSPORTS:
        raise ValueError(
            f"transporte inválido: {transport!r} (use: {', '.join(TRANSPORTS)})"
        )

    auxes_raw = env.get("VMIXER_AUXES")
    if auxes_raw:
        auxes = tuple(int(x) for x in auxes_raw.split(",") if x.strip())
    else:
        auxes = tuple(int(x) for x in (aux.get("numeros") or [1, 2, 3, 4, 5, 6, 7, 8]))

    return Settings(
        transport=transport,
        telnet_host=str(
            env.get("VMIXER_TELNET_HOST") or mesa.get("ip") or "192.168.0.50"
        ),
        telnet_port=int(
            env.get("VMIXER_TELNET_PORT") or mesa.get("porta") or 8023
        ),
        serial_port=str(
            env.get("VMIXER_SERIAL_PORT")
            or serial.get("dispositivo")
            or "/dev/ttyUSB0"
        ),
        baud=int(env.get("VMIXER_BAUD") or serial.get("baud") or 115200),
        listen_host=str(web.get("endereco") or "0.0.0.0"),
        listen_port=int(web.get("porta") or 8080),
        auxes=auxes,
        config_path=found,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib  # type: ignore

    with path.open("rb") as fh:
        loaded = tomllib.load(fh)
    return loaded if isinstance(loaded, dict) else {}
