"""Entry point — starts the FastAPI/uvicorn server."""
from __future__ import annotations

import logging

import uvicorn

from autobot.config import get_settings
from autobot.webhook_server import app  # noqa: F401 — imported for uvicorn

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(
        "autobot.webhook_server:app",
        host=s.webhook_host,
        port=s.webhook_port,
        reload=False,
    )
