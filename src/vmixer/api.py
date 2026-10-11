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
from .settings import load_settings
from .telnet_transport import FakeTelnetTransport, TelnetTransport

log = logging.getLogger(__name__)

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))

# App state
_cache: Optional[ParamCache] = None
_client: Optional[MixerClient] = None
_poller: Optional[SnapshotPoller] = None
_flusher: Optional[DirtyFlusher] = None


def _build_runtime():
    global _cache, _client, _poller, _flusher
    settings = load_settings()
    if settings.config_path:
        log.info("config: %s", settings.config_path)
    _cache = ParamCache(auxes=list(settings.auxes))
    if settings.transport == "serial":
        log.info("opening serial %s @ %s", settings.serial_port, settings.baud)
        transport = SerialTransport(settings.serial_port, baudrate=settings.baud)
    elif settings.transport == "telnet":
        log.info("opening telnet %s:%s", settings.telnet_host, settings.telnet_port)
        transport = TelnetTransport(settings.telnet_host, port=settings.telnet_port)
    elif settings.transport == "fake-telnet":
        log.info("using fake telnet transport")
        transport = FakeTelnetTransport()
    else:
        log.info("using fake transport")
        transport = FakeTransport()
    _client = MixerClient(transport)
    _poller = SnapshotPoller(_client, _cache)
    _flusher = DirtyFlusher(_client, _cache)
    _poller.start()
    _flusher.start()


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request, vmixer_aux: Optional[str] = Cookie(default=None)):
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
