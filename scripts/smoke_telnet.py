#!/usr/bin/env python3
"""Smoke test against M-200i Telnet server (LAN TCP 8023)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmixer.client import MixerClient
from vmixer.telnet_transport import TelnetTransport


def main() -> int:
    p = argparse.ArgumentParser(description="V-Mixer Telnet smoke test")
    p.add_argument("--host", required=True, help="M-200i LAN IP")
    p.add_argument("--port", type=int, default=8023)
    p.add_argument("--channel", type=int, default=1)
    p.add_argument("--aux", type=int, default=1)
    args = p.parse_args()

    print(f"connecting telnet {args.host}:{args.port}…")
    transport = TelnetTransport(args.host, port=args.port)
    client = MixerClient(transport, default_timeout=2.0)
    try:
        ver = client.version()
        print(f"VRQ -> {ver}")
        send = client.query_aux(args.channel, args.aux)
        print(
            f"AXQ I{args.channel} AX{args.aux} -> "
            f"level={send.level_db} pan={send.pan}"
        )
        try:
            name = client.query_name(args.channel)
            print(f"CNQ I{args.channel} -> {name!r}")
        except Exception as e:
            print(f"CNQ skipped: {e}")
        print("SMOKE OK")
        return 0
    except Exception as e:
        print(f"SMOKE FAIL: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
