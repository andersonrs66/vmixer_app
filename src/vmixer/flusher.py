"""Flush dirty cache cells to the mixer via AXC."""

from __future__ import annotations

import logging
import math
import threading
from typing import Optional

from .cache import ParamCache
from .client import MixerClient
from .commands import normalize_pan_for_set
from .protocol import format_level

log = logging.getLogger(__name__)


def _norm_db(level: float) -> float:
    if level == float("-inf") or (
        isinstance(level, float) and math.isinf(level) and level < 0
    ):
        return float("-inf")
    if level <= -80.0:
        return float("-inf")
    return round(level, 1)


def _levels_match(a: float, b: float) -> bool:
    na, nb = _norm_db(a), _norm_db(b)
    if na == float("-inf") and nb == float("-inf"):
        return True
    if na == float("-inf") or nb == float("-inf"):
        return False
    return abs(na - nb) < 0.15


def _pans_match(a: str, b: str) -> bool:
    return normalize_pan_for_set(a) == normalize_pan_for_set(b)


class DirtyFlusher:
    def __init__(
        self,
        client: MixerClient,
        cache: ParamCache,
        interval: float = 0.3,
        max_per_tick: int = 16,
    ) -> None:
        self._client = client
        self._cache = cache
        self._interval = interval
        self._max = max_per_tick
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vmixer-flusher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def send_cell(self, ch: int, aux: int, *, verify: bool = True) -> bool:
        """Push one cache cell to the mixer. verify=False is the live-hold path."""
        cell = self._cache.get(ch, aux)
        try:
            level = (
                "INF"
                if _norm_db(cell.level_db) == float("-inf")
                else format_level(cell.level_db)
            )
            self._client.set_aux(ch, aux, level, cell.pan)
            if not verify:
                return True
            # Keep dirty until the mixer reports our value — otherwise the
            # poller can stomp the cache with a stale AXQ right after ACK.
            send = self._client.query_aux(ch, aux)
            if _levels_match(send.level_db, cell.level_db) and _pans_match(
                send.pan, cell.pan
            ):
                self._cache.clear_dirty(ch, aux)
                return True
            log.warning(
                "flush verify mismatch I%d AX%d want=%s/%s got=%s/%s — retry",
                ch,
                aux,
                cell.level_db,
                cell.pan,
                send.level_db,
                send.pan,
            )
            return False
        except Exception as e:
            log.warning("flush I%d AX%d failed: %s — keep dirty", ch, aux, e)
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            dirty = self._cache.dirty_cells()[: self._max]
            for ch, aux, _cell in dirty:
                self.send_cell(ch, aux, verify=True)
            self._stop.wait(self._interval)
