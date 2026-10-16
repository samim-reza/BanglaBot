"""Structured logging: stdlib root logger + structlog JSON output, with phone numbers,
emails, tokens and keys scrubbed from every event (``app.core.log_redaction``)."""

import logging

import structlog

from app.core.config import get_settings
from app.core.log_redaction import install_access_log_filter, install_stdlib_filter, redact_event


def configure_logging() -> None:
    settings = get_settings()
    level = logging.getLevelName(settings.log_level.upper())
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            redact_event,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    install_access_log_filter()
    install_stdlib_filter()
