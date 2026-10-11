# app_vmixer

App multi-usuário no Raspberry Pi para ajustar **AUX sends** da Roland M-200i via **RS-232C** ou **Telnet/LAN** (protocolo V-Mixer ASCII).

## Ideia

1. Bridge serial **ou** Telnet TCP com a mesa
2. Snapshot periódico dos AUX sends → cache
3. Web/API: cada usuário escolhe um AUX e move faders (atualiza cache + dirty)
4. Flush periódico: só parâmetros dirty vão para a mesa (`AXC`)

## Fonte do protocolo

- [`V-Mixer_RS-232C_v22_e01.pdf`](../V-Mixer_RS-232C_v22_e01.pdf)
- *M-200i Telnet Reference*: mesmos comandos; sem `stx`; `ack` → texto `OK`; porta **8023**

## Configuração

Edite [`config.toml`](config.toml): transporte, IP da mesa, porta Telnet, serial e AUXes.

```toml
transporte = "telnet"

[mesa]
ip = "192.168.0.50"
porta = 8023
```

No Raspberry Pi, depois de salvar: `sudo systemctl restart vmixer`.

## Quick start (sem mesa)

```bash
cd app_vmixer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
export PYTHONPATH=src
python -m vmixer
```

O padrão em `config.toml` é `transporte = "fake"` (UI sem mesa).

## Com mesa — Telnet (LAN)

Em `config.toml`: `transporte = "telnet"` e o IP da M-200i (porta **LAN**, não REAC).

```bash
export PYTHONPATH=src
python -m vmixer
python scripts/smoke_telnet.py --host 192.168.x.x
```

## Com mesa — USB-serial

```toml
transporte = "serial"
[serial]
dispositivo = "/dev/ttyUSB0"
baud = 115200
```

## Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/decisions/](docs/decisions/)
- [docs/deploy.md](docs/deploy.md)
