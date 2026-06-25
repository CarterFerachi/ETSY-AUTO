"""
Discord bot — two jobs:
1. Poll for ✅/❌ reactions on pipeline-generated design approval messages.
2. Watch for images posted by the owner in the approval channel and auto-publish them.

Owner drop flow:
  - You post an image in the approval channel with a caption (the listing title).
  - Bot downloads it, uploads to Printify, publishes to Etsy.
  - No generation step, no approval wait — you posted it, it's approved.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx

from .config import get_settings
from .discord_approval import mark_approved, mark_rejected

log = logging.getLogger(__name__)

_DISCORD_API = "https://discord.com/api/v10"
_running = False
_seen_message_ids: set[str] = set()  # prevents reprocessing on restart


# ---------------------------------------------------------------------------
# Reaction poller (existing — pipeline approval flow)
# ---------------------------------------------------------------------------

async def _poll_reactions(message_id: str, channel_id: str, token: str) -> None:
    """Poll for ✅ (approve) or ❌ (reject) reactions every 15 seconds."""
    headers = {"Authorization": f"Bot {token}"}
    base = f"{_DISCORD_API}/channels/{channel_id}/messages/{message_id}/reactions"
    approve_url = f"{base}/%E2%9C%85"  # ✅
    reject_url = f"{base}/%E2%9D%8C"   # ❌

    async with httpx.AsyncClient(timeout=15) as client:
        while _running:
            try:
                r = await client.get(approve_url, headers=headers)
                if r.is_success:
                    non_bot = [u for u in r.json() if not u.get("bot")]
                    if non_bot:
                        mark_approved(message_id)
                        log.info("✅ reaction detected on message %s — instant approve", message_id)
                        await client.post(
                            f"{_DISCORD_API}/channels/{channel_id}/messages",
                            headers={**headers, "Content-Type": "application/json"},
                            json={"content": "✅ Design approved — publishing to Etsy now!"},
                        )
                        return

                r = await client.get(reject_url, headers=headers)
                if r.is_success:
                    non_bot = [u for u in r.json() if not u.get("bot")]
                    if non_bot:
                        mark_rejected(message_id)
                        log.info("❌ reaction detected on message %s — rejected", message_id)
                        await client.post(
                            f"{_DISCORD_API}/channels/{channel_id}/messages",
                            headers={**headers, "Content-Type": "application/json"},
                            json={"content": "🚫 Design rejected — skipping this listing."},
                        )
                        return
            except Exception as exc:
                log.warning("Reaction poll error: %s", exc)
            await asyncio.sleep(15)


_poll_tasks: list[asyncio.Task] = []


async def watch_message(message_id: str) -> None:
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


# ---------------------------------------------------------------------------
# Owner-drop listener (new — you post a design, it auto-publishes)
# ---------------------------------------------------------------------------

async def _handle_owner_drop(message: dict, channel_id: str, token: str) -> None:
    """Download the attached image and push it straight to Printify + Etsy."""
    # Lazy import to avoid circular deps
    from .pipeline import _make_title, _make_description, _make_tags
    from .printify_agent import create_product, publish_product, upload_image
    from .config import get_settings

    settings = get_settings()
    msg_id = message["id"]
    attachments = message.get("attachments", [])
    if not attachments:
        return

    attachment = attachments[0]
    image_url = attachment["url"]
    # Caption (message content) is the title; fall back to filename
    caption = (message.get("content") or "").strip()
    keyword = caption or attachment.get("filename", "custom design").rsplit(".", 1)[0]

    log.info("Owner drop detected — keyword=%r image=%s", keyword, image_url)
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        # Acknowledge in Discord
        await client.post(
            f"{_DISCORD_API}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": f"📥 Got it! Publishing **{keyword}** to Etsy now…"},
        )

        # Download the image
        dl = await client.get(image_url, timeout=60)
        dl.raise_for_status()

    tmp = Path(tempfile.mkdtemp()) / f"drop_{msg_id}.png"
    tmp.write_bytes(dl.content)

    try:
        image_id = await upload_image(tmp)
        title = _make_title(keyword)
        description = _make_description(keyword)
        tags = _make_tags(keyword)

        product_id = await create_product(
            title=title,
            description=description,
            image_id=image_id,
            tags=tags,
            retail_price_cents=int(settings.base_price_usd * 100),
        )
        await publish_product(product_id)

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                json={"content": f"✅ **{keyword}** is live on Etsy! (Printify product `{product_id}`)"},
            )
        log.info("Owner drop published: keyword=%r product_id=%s", keyword, product_id)

    except Exception:
        log.exception("Failed to publish owner drop: keyword=%r", keyword)
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                json={"content": f"❌ Failed to publish **{keyword}** — check Railway logs."},
            )
    finally:
        tmp.unlink(missing_ok=True)


async def _poll_owner_drops(channel_id: str, token: str, owner_id: str) -> None:
    """
    Poll the approval channel every 30 seconds for new messages from the owner
    that contain image attachments. When found, auto-publish without approval wait.
    """
    headers = {"Authorization": f"Bot {token}"}
    last_message_id: str | None = None

    async with httpx.AsyncClient(timeout=15) as client:
        # Seed last_message_id so we don't reprocess old messages on startup
        try:
            r = await client.get(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers=headers,
                params={"limit": 1},
            )
            if r.is_success and r.json():
                last_message_id = r.json()[0]["id"]
                _seen_message_ids.add(last_message_id)
        except Exception as exc:
            log.warning("Could not seed last_message_id: %s", exc)

    while _running:
        await asyncio.sleep(30)
        try:
            params: dict = {"limit": 10}
            if last_message_id:
                params["after"] = last_message_id

            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_DISCORD_API}/channels/{channel_id}/messages",
                    headers=headers,
                    params=params,
                )
            if not r.is_success:
                continue

            messages = r.json()
            if not messages:
                continue

            # Messages come newest-first; process oldest-first
            for msg in reversed(messages):
                mid = msg["id"]
                if mid in _seen_message_ids:
                    continue
                _seen_message_ids.add(mid)
                last_message_id = mid

                author = msg.get("author", {})
                # Only act on messages from the owner (not the bot itself)
                if author.get("id") != owner_id or author.get("bot"):
                    continue
                if not msg.get("attachments"):
                    continue

                # Fire and forget so the poll loop isn't blocked
                asyncio.create_task(_handle_owner_drop(msg, channel_id, token))

        except Exception as exc:
            log.warning("Owner-drop poll error: %s", exc)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def start_bot() -> None:
    global _running
    _running = True
    settings = get_settings()

    if settings.discord_bot_token and settings.discord_owner_id:
        asyncio.create_task(
            _poll_owner_drops(
                str(settings.discord_approval_channel_id),
                settings.discord_bot_token,
                settings.discord_owner_id,
            )
        )
        log.info("Discord owner-drop listener started (owner_id=%s)", settings.discord_owner_id)
    else:
        log.info("Discord owner-drop listener disabled (no bot token or owner ID)")

    log.info("Discord reaction poller started")


async def stop_bot() -> None:
    global _running
    _running = False
    for task in _poll_tasks:
        task.cancel()
    log.info("Discord reaction poller stopped")
