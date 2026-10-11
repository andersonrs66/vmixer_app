# ADR-0003: REAC continua listener-only

- **Status:** aceito
- **Data:** 2026-09-10

## Contexto

Etapa 1 captura áudio REAC. Handshake split / anúncio slave não é necessário para RX do broadcast da mesa.

## Decisão

O caminho REAC permanece **apenas listener** (sem anúncio TX). O app V-Mixer é independente e usa só RS-232C.

## Consequências

- Positivas: menos risco na rede REAC; escopos separados
- Negativas: sem TX de áudio / join como slave
