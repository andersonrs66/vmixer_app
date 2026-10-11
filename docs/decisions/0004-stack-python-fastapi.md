# ADR-0004: Stack Python + FastAPI

- **Status:** aceito
- **Data:** 2026-09-10

## Contexto

App no Raspberry Pi: serial + web + API + loops de poll/flush.

## Decisão

Python 3 + FastAPI + Uvicorn + pyserial + Jinja2 templates.

## Consequências

- Positivas: iteração rápida; bom ecossistema serial; deploy simples no Pi
- Negativas: GIL (mitigado com threads + asyncio to_thread); não é binário único
