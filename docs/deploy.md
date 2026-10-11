# Deploy no Raspberry Pi

IP da mesa, transporte e AUXes ficam em [`../config.toml`](../config.toml). Depois de editar:

```bash
sudo systemctl restart vmixer
```

## Opção A — Telnet / LAN (recomendado para teste rápido)

1. Conecte a M-200i na mesma rede (porta **LAN**, não REAC)
2. Configure IP da mesa (DHCP ou fixo)
3. Servidor Telnet na porta **TCP 8023**
4. Em `config.toml`: `transporte = "telnet"` e `[mesa] ip = "..."` 

```bash
cd app_vmixer
source .venv/bin/activate
export PYTHONPATH=src
python -m vmixer
```

Smoke:

```bash
PYTHONPATH=src python scripts/smoke_telnet.py --host 192.168.0.50
```

## Opção B — RS-232C / USB-serial

1. Cabo RS-232C (ou USB-serial) na porta RS-232C da M-200i
2. Na mesa: **RS-232C/MIDI SELECT** → **RS-232C**
3. Baud: **115200**, 8N1, Xon/Xoff

Em `config.toml`: `transporte = "serial"` e `[serial] dispositivo = "/dev/ttyUSB0"`.

```bash
export PYTHONPATH=src
python -m vmixer
```

Usuário no grupo `dialout` para a serial sem root.

## Fake (lab)

```bash
# em config.toml: transporte = "fake"  (ou fake-telnet)
export PYTHONPATH=src
python -m vmixer
```

## Checklist de teste com mesa

- [ ] `smoke_telnet.py` (ou serial) imprime versão e um `AXS`
- [ ] `http://<pi>:8080/` → lista de AUXes
- [ ] Escolher AUX → faders / apelidos
- [ ] Mover fader → dirty → nível muda na mesa em &lt;1 s
- [ ] Ajuste no painel físico → UI atualiza após poll
- [ ] Dois browsers no mesmo AUX compartilham estado (MVP)

## systemd (Telnet)

```ini
[Unit]
Description=V-Mixer AUX web
After=network.target

[Service]
WorkingDirectory=/home/pi/roland/app_vmixer
Environment=PYTHONPATH=src
ExecStart=/home/pi/roland/app_vmixer/.venv/bin/python -m vmixer
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
