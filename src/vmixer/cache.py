"""In-memory AUX send cache with dirty tracking."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

# While the user holds a fader, skip poller/flusher so live AXC is the only writer.
HOLD_TTL_SEC = 3.0


@dataclass
class Cell:
    level_db: float = float("-inf")
    pan: str = "C"
    dirty: bool = False
    name: str = ""
    held: bool = False
    held_at: float = 0.0


def _held_active(cell: Cell, now: Optional[float] = None) -> bool:
    if not cell.held:
        return False
    t = time.time() if now is None else now
    return (t - cell.held_at) < HOLD_TTL_SEC


@dataclass
class ParamCache:
    channels: range = field(default_factory=lambda: range(1, 33))
    auxes: list[int] = field(default_factory=lambda: list(range(1, 9)))
    _cells: dict[tuple[int, int], Cell] = field(default_factory=dict)
    _aux_names: dict[int, str] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    last_synced_at: float = 0.0
    connected: bool = False
    version: str = ""

    def __post_init__(self) -> None:
        for c in self.channels:
            for a in self.auxes:
                self._cells[(c, a)] = Cell()
        for a in self.auxes:
            self._aux_names[a] = ""

    def apply_from_mixer(
        self, channel: int, aux: int, level_db: float, pan: str
    ) -> None:
        """Update from poller — skip if dirty or currently held."""
        with self._lock:
            cell = self._cells[(channel, aux)]
            if cell.dirty or _held_active(cell):
                return
            cell.level_db = level_db
            cell.pan = pan
            self.last_synced_at = time.time()

    def set_name(self, channel: int, name: str) -> None:
        with self._lock:
            for a in self.auxes:
                self._cells[(channel, a)].name = name

    def set_aux_name(self, aux: int, name: str) -> None:
        with self._lock:
            self._aux_names[aux] = name

    def get_aux_name(self, aux: int) -> str:
        with self._lock:
            return self._aux_names.get(aux, "")

    def aux_list(self) -> list[dict]:
        with self._lock:
            out = []
            for a in self.auxes:
                n = (self._aux_names.get(a) or "").strip()
                out.append({"id": a, "name": n or f"AUX {a}", "label": n})
            return out

    def set_user_level(
        self,
        channel: int,
        aux: int,
        level_db: float,
        pan: Optional[str] = None,
        held: bool = False,
    ) -> None:
        with self._lock:
            cell = self._cells[(channel, aux)]
            # Normalize UI −∞ sentinel to mixer INF
            cell.level_db = float("-inf") if level_db <= -80.0 else float(level_db)
            if pan is not None:
                cell.pan = pan
            cell.dirty = True
            cell.held = held
            cell.held_at = time.time() if held else 0.0

    def dirty_cells(self) -> list[tuple[int, int, Cell]]:
        now = time.time()
        with self._lock:
            return [
                (c, a, Cell(level_db=cell.level_db, pan=cell.pan, dirty=True, name=cell.name))
                for (c, a), cell in self._cells.items()
                if cell.dirty and not _held_active(cell, now)
            ]

    def clear_dirty(self, channel: int, aux: int) -> None:
        with self._lock:
            cell = self._cells[(channel, aux)]
            cell.dirty = False
            cell.held = False
            cell.held_at = 0.0

    def get(self, channel: int, aux: int) -> Cell:
        with self._lock:
            cell = self._cells[(channel, aux)]
            return Cell(
                level_db=cell.level_db,
                pan=cell.pan,
                dirty=cell.dirty,
                name=cell.name,
                held=cell.held,
                held_at=cell.held_at,
            )

    def aux_snapshot(self, aux: int) -> list[dict]:
        with self._lock:
            rows = []
            for c in self.channels:
                cell = self._cells[(c, aux)]
                lv = cell.level_db
                rows.append(
                    {
                        "channel": c,
                        "name": (cell.name.strip() if cell.name else "") or f"CH{c}",
                        "level_db": None if lv == float("-inf") else lv,
                        "level_label": "INF" if lv == float("-inf") else f"{lv:.1f}",
                        "pan": cell.pan,
                        "dirty": cell.dirty,
                    }
                )
            return rows

    def full_snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self.connected,
                "version": self.version,
                "last_synced_at": self.last_synced_at,
                "auxes": self.auxes,
                "aux_names": {
                    a: (self._aux_names.get(a) or "").strip() or f"AUX {a}"
                    for a in self.auxes
                },
                "dirty_count": sum(1 for cell in self._cells.values() if cell.dirty),
                "cells": {
                    f"I{c}-AX{a}": {
                        "level_db": None
                        if cell.level_db == float("-inf")
                        else cell.level_db,
                        "pan": cell.pan,
                        "dirty": cell.dirty,
                    }
                    for (c, a), cell in self._cells.items()
                },
            }

    def iter_cells(self) -> Iterable[tuple[int, int]]:
        for a in self.auxes:
            for c in self.channels:
                yield c, a
