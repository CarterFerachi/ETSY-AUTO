"""
Discord design approval flow.

Posts the design image to a Discord channel with ❌ reaction instructions.
Waits up to approval_timeout_seconds. If user reacts ❌ → rejected.
If timeout passes with no rejection → approved (auto-publish).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

# In-memory set of rejected message IDs (populated by webhook_server)
_rejected: set[str] = set()


def mark_rejected(message_id: str) -> None:
    """Called by webhook server when user reacts ❌ to a design."""
    _rejected.add(message_id)


async def post_for_approval(title: str, image_path: Path, image_url: str) -> str | None:
    """
    Post design to Discord. Returns message_id, or None if webhook not configured.
    """
    settings = get_settings()
    if not settings.discord_webhook_url:
        log.warning("No DISCORD_WEBHOOK_URL set — skipping approval step")
        return None

    timeout = settings.approval_timeout_seconds
    payload = {
        "embeds": [
            {
                "title": f"🎨 New Design Ready",
                "description": (
                    f"**{title}**\n\n"
                    f"React with ❌ within {timeout // 60} minutes to **reject**.\n"
                    f"No reaction = auto-publishes to Etsy."
                ),
                "image": {"url": image_url},
                "color": 3066993,
            }
        ]
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            settings.discord_webhook_url + "?wait=true",
            json=payload,
        )
        r.raise_for_status()

    message_id: str = r.json()["id"]
    log.info("Posted design to Discord — message_id=%s", message_id)

    # Start polling for ❌ reactions
    from .discord_bot import watch_message
    await watch_message(message_id)

    return message_id


async def wait_for_approval(message_id: str) -> bool:
    """
    Wait up to timeout seconds. Returns True (approved) or False (rejected).
    """
    settings = get_settings()
    timeout = settings.approval_timeout_seconds
    elapsed = 0

    while elapsed < timeout:
        if message_id in _rejected:
            _rejected.discard(message_id)
            log.info("Design rejected via Discord (message_id=%s)", message_id)
            return False
        await asyncio.sleep(15)
        elapsed += 15

    log.info("Design approved by timeout (message_id=%s)", message_id)
    return True
