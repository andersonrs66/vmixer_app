"""Background snapshot poller (round-robin AXQ + CNQ names)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .cache import ParamCache
from .client import MixerClient
from .commands import aux_token

log = logging.getLogger(__name__)


class SnapshotPoller:
    def __init__(
        self,
        client: MixerClient,
        cache: ParamCache,
        cells_per_tick: int = 8,
        tick_interval: float = 0.05,
        names_per_tick: int = 2,
    ) -> None:
        self._client = client
        self._cache = cache
        self._cells_per_tick = cells_per_tick
        self._tick_interval = tick_interval
        self._names_per_tick = names_per_tick
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._order = list(cache.iter_cells())
        self._idx = 0
        self._name_channels = list(cache.channels)
        self._name_idx = 0
        self._aux_name_list = list(cache.auxes)
        self._aux_name_idx = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vmixer-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _refresh_channel_names(self, count: int) -> None:
        if not self._name_channels:
            return
        for _ in range(count):
            if self._stop.is_set():
                return
            ch = self._name_channels[self._name_idx % len(self._name_channels)]
            self._name_idx += 1
            try:
                name = self._client.query_name(ch)
                self._cache.set_name(ch, (name or "").strip())
            except Exception as e:
                log.warning("CNQ I%d failed: %s", ch, e)

    def _refresh_aux_names(self, count: int) -> None:
        if not self._aux_name_list:
            return
        for _ in range(count):
            if self._stop.is_set():
                return
            aux = self._aux_name_list[self._aux_name_idx % len(self._aux_name_list)]
            self._aux_name_idx += 1
            try:
                name = self._client.query_aux_name(aux)
                cleaned = (name or "").strip()
                self._cache.set_aux_name(aux, cleaned)
                log.debug("name %s -> %r", aux_token(aux), cleaned)
            except Exception as e:
                log.warning("CNQ AX%d failed: %s", aux, e)

    def _run(self) -> None:
        try:
            ver = self._client.version()
            self._cache.version = ver
            self._cache.connected = True
            log.info("mixer version: %s", ver)
        except Exception as e:
            log.warning("version query failed: %s", e)
            self._cache.connected = False

        log.info("refreshing AUX names…")
        self._refresh_aux_names(len(self._aux_name_list))
        log.info("refreshing channel names (I1–I%d)…", len(self._name_channels))
        self._refresh_channel_names(len(self._name_channels))

        while not self._stop.is_set():
            for _ in range(self._cells_per_tick):
                if self._stop.is_set():
                    break
                if not self._order:
                    break
                ch, aux = self._order[self._idx % len(self._order)]
                self._idx += 1
                try:
                    send = self._client.query_aux(ch, aux)
                    self._cache.apply_from_mixer(
                        send.channel, send.aux, send.level_db, send.pan
                    )
                except Exception as e:
                    log.debug("poll I%d AX%d failed: %s", ch, aux, e)
                    self._cache.connected = False
                else:
                    self._cache.connected = True

            self._refresh_channel_names(self._names_per_tick)
            self._refresh_aux_names(1)
            self._stop.wait(self._tick_interval)
