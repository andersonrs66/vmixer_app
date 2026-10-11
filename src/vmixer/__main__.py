"""python -m vmixer — sobe a UI lendo config.toml."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    from .settings import load_settings

    settings = load_settings()
    uvicorn.run(
        "vmixer.api:app",
        host=settings.listen_host,
        port=settings.listen_port,
    )


if __name__ == "__main__":
    main()
