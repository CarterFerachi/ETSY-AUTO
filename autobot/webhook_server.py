"""
FastAPI webhook server.

Endpoints:
  GET  /health          — liveness probe
  POST /webhooks/etsy   — receives Etsy order notifications
  POST /admin/run-now   — manually trigger the pipeline (protected by API key)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .fulfillment import fulfill_etsy_order
from .pipeline import run_pipeline
from .scheduler import start_scheduler, stop_scheduler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Etsy-Printify Autobot", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Etsy order webhook
# ---------------------------------------------------------------------------

def _verify_etsy_signature(body: bytes, signature: str | None) -> None:
    """Validate Etsy's HMAC-SHA256 webhook signature."""
    settings = get_settings()
    secret = settings.etsy_webhook_secret
    if not secret:
        return  # signature validation disabled (dev mode)

    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Etsy-Signature")

    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@app.post("/webhooks/etsy", status_code=status.HTTP_202_ACCEPTED)
async def etsy_webhook(
    request: Request,
    x_etsy_signature: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()
    _verify_etsy_signature(body, x_etsy_signature)

    payload: dict[str, Any] = await request.json()
    event_type: str = payload.get("event", "")
    log.info("Etsy webhook received: event=%r", event_type)

    if event_type == "receipt.created":
        receipt_id = str(payload.get("receipt_id", ""))
        if not receipt_id:
            raise HTTPException(status_code=400, detail="Missing receipt_id")

        # Fire and forget — respond quickly to Etsy
        import asyncio
        asyncio.create_task(_handle_order(receipt_id))

    return JSONResponse({"received": True})


async def _handle_order(receipt_id: str) -> None:
    try:
        printify_id = await fulfill_etsy_order(receipt_id)
        log.info("Fulfilled receipt %s → Printify order %s", receipt_id, printify_id)
    except Exception:
        log.exception("Failed to fulfill receipt %s", receipt_id)


# ---------------------------------------------------------------------------
# Admin: manual pipeline trigger
# ---------------------------------------------------------------------------

@app.post("/admin/run-now", status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    x_admin_key: str | None = Header(default=None),
) -> JSONResponse:
    settings = get_settings()
    expected_key = getattr(settings, "admin_key", None) or settings.etsy_webhook_secret
    if expected_key and x_admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    import asyncio
    asyncio.create_task(run_pipeline())
    return JSONResponse({"started": True})
