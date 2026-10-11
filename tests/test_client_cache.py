from vmixer.cache import ParamCache
from vmixer.client import MixerClient
from vmixer.commands import parse_axs
from vmixer.protocol import FrameDecoder, STX
from vmixer.serial_transport import FakeTransport


def test_fake_axq_axs():
    t = FakeTransport()
    c = MixerClient(t)
    send = c.query_aux(1, 1)
    assert send.channel == 1
    assert send.aux == 1
    assert send.level_db == -6.5
    assert send.pan == "C"


def test_fake_axc_and_dirty_flush_path():
    t = FakeTransport()
    c = MixerClient(t)
    c.set_aux(5, 2, -3.0, "C")
    send = c.query_aux(5, 2)
    assert send.level_db == -3.0


def test_cache_poll_skips_dirty():
    cache = ParamCache(auxes=[1])
    cache.apply_from_mixer(1, 1, -6.5, "C")
    assert cache.get(1, 1).level_db == -6.5
    cache.set_user_level(1, 1, 0.0)
    assert cache.get(1, 1).dirty
    cache.apply_from_mixer(1, 1, -20.0, "C")  # should NOT overwrite
    assert cache.get(1, 1).level_db == 0.0
    assert cache.get(1, 1).dirty
    cache.clear_dirty(1, 1)
    cache.apply_from_mixer(1, 1, -20.0, "C")
    assert cache.get(1, 1).level_db == -20.0


def test_cache_poll_skips_held():
    cache = ParamCache(auxes=[1])
    cache.apply_from_mixer(1, 1, -6.5, "C")
    cache.set_user_level(1, 1, 1.0, held=True)
    assert cache.get(1, 1).held
    cache.apply_from_mixer(1, 1, -40.0, "C")
    assert cache.get(1, 1).level_db == 1.0
    assert cache.dirty_cells() == []


def test_parse_axs_helper():
    dec = FrameDecoder()
    msg = dec.feed(bytes([STX]) + b"AXS:I2,AX1,0.0,L10;")[0]
    send = parse_axs(msg)
    assert send.channel == 2 and send.aux == 1 and send.level_db == 0.0
    assert send.pan == "L10"


def test_parse_cns_quoted():
    from vmixer.protocol import FrameDecoder, STX
    from vmixer.commands import parse_cns

    dec = FrameDecoder()
    msg = dec.feed(bytes([STX]) + b'CNS:I1,"A.BASS";')[0]
    kind, ch, name = parse_cns(msg)
    assert kind == "I" and ch == 1
    assert name == "A.BASS"


def test_parse_cns_aux():
    from vmixer.protocol import TelnetFrameDecoder
    from vmixer.commands import parse_cns
    from vmixer.client import MixerClient
    from vmixer.serial_transport import FakeTransport

    dec = TelnetFrameDecoder()
    msg = dec.feed(b'CNS:AX2,"MON2  ";\r\n')[0]
    kind, n, name = parse_cns(msg)
    assert kind == "AX" and n == 2
    assert name == "MON2"

    c = MixerClient(FakeTransport())
    assert c.query_aux_name(1).startswith("AUX")


def test_normalize_pan_for_set():
    from vmixer.commands import normalize_pan_for_set, cmd_axc
    from vmixer.protocol import STX

    assert normalize_pan_for_set("0") == "C"
    assert normalize_pan_for_set("") == "C"
    assert normalize_pan_for_set("R30") == "R30"
    assert normalize_pan_for_set("l12") == "L12"
    raw = cmd_axc(30, 2, -3.0, "0")
    assert raw == bytes([STX]) + b"AXC:I30,AX2,-3.0,C;"
