"""Structured logging setup."""

import logging
import sys


def configure_logging(level: str) -> None:
    """Configure concise, machine-readable logs for command entry points."""

    logging.basicConfig(
        level=level,
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        stream=sys.stdout,
        force=True,
    )
