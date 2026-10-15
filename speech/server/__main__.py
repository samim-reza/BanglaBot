"""``python -m server`` (run from ``speech/``): serve with uvicorn in the foreground."""

from __future__ import annotations

import logging

import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        ws_max_size=2_000_000,
        workers=1,  # models live in-process; one process owns the GPU
    )


if __name__ == "__main__":
    main()
