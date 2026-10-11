from vmixer.protocol import FrameDecoder, STX, build_command, format_level, parse_level


def test_build_axq():
    assert build_command("AXQ", "I1", "AX3") == bytes([STX]) + b"AXQ:I1,AX3;"


def test_build_axc():
    assert build_command("AXC", "I1", "AX1", "4.0", "R30") == bytes([STX]) + b"AXC:I1,AX1,4.0,R30;"


def test_decode_axs():
    dec = FrameDecoder()
    msgs = dec.feed(bytes([STX]) + b"AXS:I1,AX3,-6.5,C;")
    assert len(msgs) == 1
    assert msgs[0].opcode == "AXS"
    assert msgs[0].params == ("I1", "AX3", "-6.5", "C")


def test_decode_ack_and_err():
    dec = FrameDecoder()
    msgs = dec.feed(bytes([0x06]))
    assert msgs[0].kind == "ack"
    msgs = dec.feed(bytes([STX]) + b"ERR:5;")
    assert msgs[0].kind == "err"
    assert msgs[0].err_code == 5


def test_level_roundtrip():
    assert format_level(-6.5) == "-6.5"
    assert format_level(float("-inf")) == "INF"
    assert parse_level("INF") == float("-inf")
    assert parse_level("-6.5") == -6.5
