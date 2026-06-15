from __future__ import annotations

import os

import structlog


def configure_logging() -> None:
    """Configure structlog for production (JSON) or dev (console)."""
    is_prod = os.environ.get("QUORUM_ENV", "").lower() in ("production", "prod")

    if is_prod:
        processors: list[structlog.types.Processor] = [
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("quorum")
