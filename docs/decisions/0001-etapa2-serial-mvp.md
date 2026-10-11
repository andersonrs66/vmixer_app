# ADR-0001: Etapa 2 via RS-232C (PDF oficial)

- **Status:** aceito
- **Data:** 2026-09-10

## Contexto

Controle remoto da M-200i precisa de um transporte documentado. O repo tem `V-Mixer_RS-232C_v22_e01.pdf`. LAN/TCP de controle não está especificado aqui.

## Decisão

MVP da Etapa 2 usa **somente RS-232C / USB-serial**, implementando o ASCII V-Mixer conforme o PDF (115200 8N1, Xon/Xoff, `stx`/`ack`/`ERR`).

## Consequências

- Positivas: comportamento previsível; testável com cabo USB-serial
- Negativas: cabo físico; LAN fica para depois
