# Arquitetura — app_vmixer (Etapa 2)

## Objetivo

Servir UI/API multi-usuário para mix de retorno (AUX) na M-200i, com cache local e sync atrasado via RS-232C.

## Fluxo

```
M-200i RS-232C
      ▲
      │ AXQ/AXS/AXC  (único mutex)
SerialBridge
      ▲
 SnapshotPoller ──► ParamCache ◄── Web/API (usuários)
 DirtyFlusher   ◄── (células dirty)
```

## Componentes

| Módulo | Papel |
|--------|--------|
| `protocol` | framing serial (`stx`/`ack`) e telnet (`OK`, sem `stx`) |
| `serial_transport` / `telnet_transport` | I/O RS-232C ou TCP:8023 |
| `commands` | tokens M-200i / parse AXS/CNS |
| `cache` | levels/pan + dirty + lock |
| `poller` | snapshot round-robin; não sobrescreve dirty |
| `flusher` | envia só dirty |
| `api` | FastAPI + UI |

## Defaults

- Serial: baud 115200, 8N1, Xon/Xoff
- Telnet: host via env, porta **8023**
- Canais `I1–I32`, AUX `AX1–AX8` (M-200i)
- `FLUSH_INTERVAL` ~300 ms; poll round-robin

## REAC

Etapa 1 permanece **listener-only** (sem anúncio). Este app não fala REAC.
