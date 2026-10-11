from pathlib import Path

from vmixer.settings import load_settings


def test_load_toml_file(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
transporte = "telnet"
[mesa]
ip = "10.0.0.8"
porta = 8023
[aux]
numeros = [1, 3]
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("VMIXER_TRANSPORT", raising=False)
    monkeypatch.delenv("VMIXER_TELNET_HOST", raising=False)
    monkeypatch.delenv("VMIXER_AUXES", raising=False)
    monkeypatch.setenv("VMIXER_CONFIG", str(cfg))
    s = load_settings()
    assert s.transport == "telnet"
    assert s.telnet_host == "10.0.0.8"
    assert s.telnet_port == 8023
    assert s.auxes == (1, 3)
    assert s.config_path == cfg


def test_env_overrides_file(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
transporte = "telnet"
[mesa]
ip = "10.0.0.8"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("VMIXER_CONFIG", str(cfg))
    monkeypatch.setenv("VMIXER_TRANSPORT", "fake")
    monkeypatch.setenv("VMIXER_TELNET_HOST", "192.168.0.9")
    s = load_settings()
    assert s.transport == "fake"
    assert s.telnet_host == "192.168.0.9"
