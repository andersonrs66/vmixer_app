from vmixer.client import MixerClient
from vmixer.protocol import TelnetFrameDecoder, build_telnet_command, telnet_ack
from vmixer.telnet_transport import FakeTelnetTransport


def test_telnet_build_no_stx():
    raw = build_telnet_command("AXQ", "I1", "AX3")
    assert raw.startswith(b"AXQ:")
    assert b"\x02" not in raw
    assert raw.endswith(b"\r\n")


def test_telnet_decoder_ok_and_axs():
    dec = TelnetFrameDecoder()
    msgs = dec.feed(b"OK\r\n")
    assert msgs[0].kind == "ack"
    msgs = dec.feed(b"AXS:I1,AX3,-6.5,C;\r\n")
    assert msgs[0].opcode == "AXS"
    assert msgs[0].params[2] == "-6.5"


def test_fake_telnet_client_roundtrip():
    c = MixerClient(FakeTelnetTransport())
    assert "M-200i" in c.version()
    send = c.query_aux(1, 1)
    assert send.level_db == -6.5
    c.set_aux(1, 1, -1.0, "C")
    assert c.query_aux(1, 1).level_db == -1.0
    name = c.query_name(2)
    assert "CH" in name or name
    c.close()


def test_telnet_ack_bytes():
    assert telnet_ack() == b"OK\r\n"
