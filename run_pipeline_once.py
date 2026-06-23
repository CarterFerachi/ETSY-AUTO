"""Convenience script: run the full pipeline once without starting the server."""
from __future__ import annotations

import asyncio
import logging

from autobot.config import get_settings
from autobot.pipeline import run_pipeline

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
