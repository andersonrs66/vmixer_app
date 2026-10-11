# ADR-0002: Snapshot / cache / dirty flush

- **Status:** aceito
- **Data:** 2026-09-10

## Contexto

A mesa não empurra mudanças locais. UI multi-usuário precisa de cache. Atraso pequeno é aceitável.

## Decisão

1. Poller preenche cache com `AXQ`/`AXS` (não sobrescreve células dirty)
2. UI/API escreve na cache e marca dirty
3. Flusher envia só dirty via `AXC` e limpa dirty no `ack`

## Consequências

- Positivas: serial não satura com writes redundantes; UI responsiva
- Negativas: atraso até o flush; possível conflito se alguém editar o mesmo AUX no painel físico durante dirty
