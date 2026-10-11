"""FastAPI app: AUX monitor mix UI + API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Cookie, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .cache import ParamCache
from .client import MixerClient
from .flusher import DirtyFlusher
from .poller import SnapshotPoller
from .serial_transport import FakeTransport, SerialTransport
from .settings import TRANSPORTS, Settings, load_settings, save_settings
from .telnet_transport import FakeTelnetTransport, TelnetTransport

log = logging.getLogger(__name__)

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))

# App state
_cache: Optional[ParamCache] = None
_client: Optional[MixerClient] = None
_poller: Optional[SnapshotPoller] = None
_flusher: Optional[DirtyFlusher] = None
_settings: Optional[Settings] = None
_link_error: Optional[str] = None


def _open_transport(settings: Settings):
    if settings.transport == "serial":
        log.info("opening serial %s @ %s", settings.serial_port, settings.baud)
        return SerialTransport(settings.serial_port, baudrate=settings.baud)
    if settings.transport == "telnet":
        log.info("opening telnet %s:%s", settings.telnet_host, settings.telnet_port)
        return TelnetTransport(settings.telnet_host, port=settings.telnet_port)
    if settings.transport == "fake-telnet":
        log.info("using fake telnet transport")
        return FakeTelnetTransport()
    log.info("using fake transport")
    return FakeTransport()


def _apply_settings(settings: Settings) -> None:
    global _cache, _client, _poller, _flusher, _settings, _link_error
    _shutdown_runtime()
    _settings = settings
    _link_error = None
    if settings.config_path:
        log.info("config: %s", settings.config_path)
    _cache = ParamCache(auxes=list(settings.auxes))
    try:
        transport = _open_transport(settings)
    except Exception as e:
        _link_error = str(e)
        _client = None
        _poller = None
        _flusher = None
        log.warning("mesa indisponível (%s): %s", settings.transport, e)
        return
    _client = MixerClient(transport)
    _poller = SnapshotPoller(_client, _cache)
    _flusher = DirtyFlusher(_client, _cache)
    _poller.start()
    _flusher.start()


def _build_runtime():
    _apply_settings(load_settings())


def _offline() -> bool:
    return bool(_link_error)


def _shutdown_runtime():
    global _poller, _flusher, _client
    if _poller:
        _poller.stop()
    if _flusher:
        _flusher.stop()
    if _client:
        _client.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    _build_runtime()
    yield
    _shutdown_runtime()


app = FastAPI(title="V-Mixer AUX", lifespan=lifespan)


class LevelUpdate(BaseModel):
    level_db: float = Field(..., ge=-80.0, le=10.0)
    pan: Optional[str] = None
    live: bool = False


@app.get("/api/health")
def health():
    assert _cache
    return {
        "ok": True,
        "connected": _cache.connected,
        "version": _cache.version,
        "dirty_count": _cache.full_snapshot()["dirty_count"],
        "last_synced_at": _cache.last_synced_at,
    }


@app.get("/api/snapshot")
def snapshot():
    assert _cache
    return _cache.full_snapshot()


@app.get("/api/aux/{aux_id}")
def get_aux(aux_id: int):
    assert _cache
    if aux_id not in _cache.auxes:
        raise HTTPException(404, "AUX not watched")
    name = _cache.get_aux_name(aux_id).strip()
    return {
        "aux": aux_id,
        "name": name or f"AUX {aux_id}",
        "channels": _cache.aux_snapshot(aux_id),
    }


@app.get("/api/auxes")
def list_auxes():
    assert _cache
    return {"auxes": _cache.aux_list()}


@app.put("/api/aux/{aux_id}/channel/{ch}")
def put_aux_channel(aux_id: int, ch: int, body: LevelUpdate):
    assert _cache
    assert _flusher
    if aux_id not in _cache.auxes or not 1 <= ch <= 32:
        raise HTTPException(404, "invalid channel/aux")
    _cache.set_user_level(ch, aux_id, body.level_db, body.pan, held=body.live)
    synced = _flusher.send_cell(ch, aux_id, verify=not body.live)
    return {
        "ok": True,
        "channel": ch,
        "aux": aux_id,
        "level_db": body.level_db,
        "live": body.live,
        "synced": synced,
    }


@app.post("/api/session")
def set_session(aux: int = Form(...)):
    assert _cache
    if aux not in _cache.auxes:
        raise HTTPException(400, "AUX not available")
    resp = RedirectResponse(url=f"/aux/{aux}", status_code=303)
    resp.set_cookie("vmixer_aux", str(aux), max_age=60 * 60 * 24 * 30)
    return resp


def _settings_or_default() -> Settings:
    return _settings or load_settings()


def _parse_config_form(
    transporte: str,
    mesa_ip: str,
    mesa_porta: int,
    serial_dispositivo: str,
    serial_baud: int,
    web_endereco: str,
    web_porta: int,
    aux_numeros: list[int],
) -> Settings:
    transport = transporte.strip().lower()
    if transport not in TRANSPORTS:
        raise ValueError(f"transporte inválido: {transport}")
    auxes = tuple(sorted({int(n) for n in aux_numeros}))
    if not auxes or any(n < 1 or n > 8 for n in auxes):
        raise ValueError("escolha AUXes entre 1 e 8")
    ip = mesa_ip.strip()
    device = serial_dispositivo.strip()
    host = web_endereco.strip()
    if not ip or not device or not host:
        raise ValueError("IP, dispositivo serial e endereço web são obrigatórios")
    if not 1 <= int(mesa_porta) <= 65535 or not 1 <= int(web_porta) <= 65535:
        raise ValueError("porta fora do intervalo 1–65535")
    if int(serial_baud) <= 0:
        raise ValueError("baud inválido")
    current = _settings_or_default()
    return Settings(
        transport=transport,
        telnet_host=ip,
        telnet_port=int(mesa_porta),
        serial_port=device,
        baud=int(serial_baud),
        listen_host=host,
        listen_port=int(web_porta),
        auxes=auxes,
        config_path=current.config_path,
    )


def _config_context(request: Request, error: Optional[str] = None, saved: bool = False):
    settings = _settings_or_default()
    web_changed = False
    return {
        "request": request,
        "settings": settings,
        "aux_selected": set(settings.auxes),
        "transports": TRANSPORTS,
        "error": error or _link_error,
        "saved": saved,
        "web_changed": web_changed,
        "offline": _offline(),
    }


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "config.html", _config_context(request))


@app.post("/config", response_class=HTMLResponse)
def config_save(
    request: Request,
    transporte: str = Form(...),
    mesa_ip: str = Form(...),
    mesa_porta: int = Form(...),
    serial_dispositivo: str = Form(...),
    serial_baud: int = Form(...),
    web_endereco: str = Form(...),
    web_porta: int = Form(...),
    aux_numeros: list[int] = Form(default=[]),
):
    current = _settings_or_default()
    try:
        settings = _parse_config_form(
            transporte,
            mesa_ip,
            mesa_porta,
            serial_dispositivo,
            serial_baud,
            web_endereco,
            web_porta,
            aux_numeros,
        )
    except ValueError as e:
        ctx = _config_context(request, error=str(e))
        ctx["settings"] = Settings(
            transport=transporte.strip().lower() or current.transport,
            telnet_host=mesa_ip.strip() or current.telnet_host,
            telnet_port=mesa_porta,
            serial_port=serial_dispositivo.strip() or current.serial_port,
            baud=serial_baud,
            listen_host=web_endereco.strip() or current.listen_host,
            listen_port=web_porta,
            auxes=tuple(aux_numeros) or current.auxes,
            config_path=current.config_path,
        )
        ctx["aux_selected"] = set(ctx["settings"].auxes)
        return TEMPLATES.TemplateResponse(request, "config.html", ctx, status_code=400)

    path = save_settings(settings)
    web_changed = (
        settings.listen_host != current.listen_host
        or settings.listen_port != current.listen_port
    )
    _apply_settings(Settings(
        transport=settings.transport,
        telnet_host=settings.telnet_host,
        telnet_port=settings.telnet_port,
        serial_port=settings.serial_port,
        baud=settings.baud,
        listen_host=settings.listen_host,
        listen_port=settings.listen_port,
        auxes=settings.auxes,
        config_path=path,
    ))
    if _link_error:
        ctx = _config_context(request)
        ctx["saved"] = True
        ctx["web_changed"] = web_changed
        return TEMPLATES.TemplateResponse(request, "config.html", ctx)
    if web_changed:
        ctx = _config_context(request)
        ctx["saved"] = True
        ctx["web_changed"] = True
        ctx["error"] = None
        return TEMPLATES.TemplateResponse(request, "config.html", ctx)
    return RedirectResponse(url="/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, vmixer_aux: Optional[str] = Cookie(default=None)):
    if _offline():
        return RedirectResponse(url="/config", status_code=303)
    assert _cache
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "auxes": _cache.aux_list(),
            "selected": int(vmixer_aux) if vmixer_aux else None,
            "health": health(),
        },
    )


@app.get("/aux/{aux_id}", response_class=HTMLResponse)
def aux_page(request: Request, aux_id: int):
    if _offline():
        return RedirectResponse(url="/config", status_code=303)
    assert _cache
    if aux_id not in _cache.auxes:
        raise HTTPException(404)
    aux_name = _cache.get_aux_name(aux_id).strip() or f"AUX {aux_id}"
    return TEMPLATES.TemplateResponse(
        request,
        "aux.html",
        {
            "aux": aux_id,
            "aux_name": aux_name,
            "channels": _cache.aux_snapshot(aux_id),
            "health": health(),
        },
    )


@app.post("/aux/{aux_id}/channel/{ch}", response_class=HTMLResponse)
def aux_channel_form(
    request: Request,
    aux_id: int,
    ch: int,
    level_db: float = Form(...),
):
    assert _cache
    assert _flusher
    level_db = max(-80.0, min(10.0, level_db))
    _cache.set_user_level(ch, aux_id, level_db)
    _flusher.send_cell(ch, aux_id, verify=True)
    return RedirectResponse(url=f"/aux/{aux_id}", status_code=303)
