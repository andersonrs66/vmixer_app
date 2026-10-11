#!/usr/bin/env python3
"""Smoke test against a real M-200i RS-232C port."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmixer.client import MixerClient
from vmixer.serial_transport import SerialTransport


def main() -> int:
    p = argparse.ArgumentParser(description="V-Mixer serial smoke test")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--channel", type=int, default=1)
    p.add_argument("--aux", type=int, default=1)
    args = p.parse_args()

    print(f"opening {args.port} @ {args.baud} (8N1 xonxoff)…")
    transport = SerialTransport(args.port, baudrate=args.baud)
    client = MixerClient(transport, default_timeout=2.0)
    try:
        ver = client.version()
        print(f"VRQ -> {ver}")
        send = client.query_aux(args.channel, args.aux)
        print(
            f"AXQ I{args.channel} AX{args.aux} -> "
            f"level={send.level_db} pan={send.pan}"
        )
        print("SMOKE OK")
        return 0
    except Exception as e:
        print(f"SMOKE FAIL: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
