"""
Discord reaction listener using raw REST API polling (no discord.py library).
Polls for ❌ reactions on design approval messages every 15 seconds.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import get_settings
from .discord_approval import mark_rejected

log = logging.getLogger(__name__)

_DISCORD_API = "https://discord.com/api/v10"
_running = False


async def _poll_reactions(message_id: str, channel_id: str, token: str) -> None:
    """Poll until ❌ reaction found or message_id removed from tracking."""
    headers = {"Authorization": f"Bot {token}"}
    url = f"{_DISCORD_API}/channels/{channel_id}/messages/{message_id}/reactions/%E2%9D%8C"

    async with httpx.AsyncClient(timeout=15) as client:
        while _running:
            try:
                r = await client.get(url, headers=headers)
                if r.is_success:
                    users = r.json()
                    # Filter out the bot itself
                    non_bot = [u for u in users if not u.get("bot")]
                    if non_bot:
                        mark_rejected(message_id)
                        log.info("❌ reaction detected on message %s", message_id)
                        # Post confirmation
                        await client.post(
                            f"{_DISCORD_API}/channels/{channel_id}/messages",
                            headers={**headers, "Content-Type": "application/json"},
                            json={"content": f"🚫 Design rejected — skipping this listing."},
                        )
                        return
            except Exception as exc:
                log.warning("Reaction poll error: %s", exc)
            await asyncio.sleep(15)


_poll_tasks: list[asyncio.Task] = []


async def watch_message(message_id: str) -> None:
    """Start polling for ❌ reactions on a message."""
    settings = get_settings()
    if not settings.discord_bot_token:
        return
    task = asyncio.create_task(
        _poll_reactions(
            message_id,
            str(settings.discord_approval_channel_id),
            settings.discord_bot_token,
        )
    )
    _poll_tasks.append(task)


async def start_bot() -> None:
    global _running
    _running = True
    log.info("Discord reaction poller started")


async def stop_bot() -> None:
    global _running
    _running = False
    for task in _poll_tasks:
        task.cancel()
    log.info("Discord reaction poller stopped")
