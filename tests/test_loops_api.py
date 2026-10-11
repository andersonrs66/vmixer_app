import time

from fastapi.testclient import TestClient

from vmixer.cache import ParamCache
from vmixer.client import MixerClient
from vmixer.flusher import DirtyFlusher
from vmixer.poller import SnapshotPoller
from vmixer.serial_transport import FakeTransport


def test_poller_and_flusher_roundtrip():
    transport = FakeTransport()
    client = MixerClient(transport)
    cache = ParamCache(auxes=[1])
    poller = SnapshotPoller(client, cache, cells_per_tick=32, tick_interval=0.02)
    flusher = DirtyFlusher(client, cache, interval=0.05)
    poller.start()
    flusher.start()
    try:
        deadline = time.time() + 3
        while time.time() < deadline and cache.get(1, 1).level_db == float("-inf"):
            time.sleep(0.05)
        assert cache.get(1, 1).level_db == -6.5

        cache.set_user_level(1, 1, 2.5)
        deadline = time.time() + 3
        while time.time() < deadline and cache.get(1, 1).dirty:
            time.sleep(0.05)
        assert not cache.get(1, 1).dirty
        assert transport.levels[(1, 1)] == 2.5
    finally:
        poller.stop()
        flusher.stop()
        client.close()


def test_api_home_and_put(monkeypatch):
    monkeypatch.setenv("VMIXER_TRANSPORT", "fake")
    monkeypatch.setenv("VMIXER_AUXES", "1,2")
    # Import fresh app lifespan via TestClient
    from vmixer import api as api_mod

    with TestClient(api_mod.app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        r = client.get("/")
        assert r.status_code == 200
        assert b"AUX" in r.content
        # wait a moment for poller
        time.sleep(0.3)
        r = client.put("/api/aux/1/channel/1", json={"level_db": -1.5})
        assert r.status_code == 200
        body = r.json()
        assert body["synced"] is True
        assert body["live"] is False
        r = client.get("/api/aux/1")
        assert r.status_code == 200
        ch1 = next(c for c in r.json()["channels"] if c["channel"] == 1)
        assert ch1["level_db"] == -1.5
        assert ch1["dirty"] is False

        live = client.put("/api/aux/1/channel/2", json={"level_db": -3.0, "live": True})
        assert live.status_code == 200
        assert live.json()["live"] is True
        ch2 = next(c for c in client.get("/api/aux/1").json()["channels"] if c["channel"] == 2)
        assert ch2["level_db"] == -3.0
        assert ch2["dirty"] is True
