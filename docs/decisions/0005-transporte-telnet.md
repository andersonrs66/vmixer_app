# ADR-0005: Transporte Telnet (LAN) além do RS-232C

- **Status:** aceito
- **Data:** 2026-09-10

## Contexto

A M-200i expõe servidor Telnet na LAN (TCP **8023**). Os opcodes são os do RS-232C; `stx` é omitido e `ack` vira texto `OK` (*M-200i Telnet Reference*).

## Decisão

Suportar `VMIXER_TRANSPORT=telnet` com `VMIXER_TELNET_HOST` / `VMIXER_TELNET_PORT` (default 8023), reutilizando `MixerClient` com framing telnet.

## Consequências

- Positivas: teste na mesa sem cabo serial; mesmo app
- Negativas: depende de LAN estável; doc Telnet oficial não está no repo (comportamento espelhado da referência pública)
