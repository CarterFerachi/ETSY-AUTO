"""
Discord bot that listens for ❌ reactions in #design-approvals.
When a user reacts ❌ to a design preview, it marks that design as rejected.
Runs as a background asyncio task alongside FastAPI.
"""
from __future__ import annotations

import asyncio
import logging

import discord

from .config import get_settings
from .discord_approval import mark_rejected

log = logging.getLogger(__name__)


class ApprovalBot(discord.Client):
    async def on_ready(self) -> None:
        log.info("Discord bot connected as %s", self.user)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        settings = get_settings()
        if payload.channel_id != settings.discord_approval_channel_id:
            return
        if str(payload.emoji) != "❌":
            return
        if payload.user_id == self.user.id:  # type: ignore[union-attr]
            return

        message_id = str(payload.message_id)
        log.info("❌ reaction received on message %s — marking rejected", message_id)
        mark_rejected(message_id)

        # Confirm rejection with a reply
        channel = self.get_channel(payload.channel_id)
        if channel:
            await channel.send(f"🚫 Design rejected (message {message_id}) — skipping.")  # type: ignore[union-attr]


_bot: ApprovalBot | None = None
_bot_task: asyncio.Task | None = None


async def start_bot() -> None:
    """Start the Discord bot as a background task."""
    global _bot, _bot_task
    settings = get_settings()
    if not settings.discord_bot_token:
        log.warning("No DISCORD_BOT_TOKEN set — bot disabled")
        return

    intents = discord.Intents.default()
    intents.reactions = True
    intents.guilds = True

    _bot = ApprovalBot(intents=intents)
    _bot_task = asyncio.create_task(_bot.start(settings.discord_bot_token))
    log.info("Discord approval bot started")


async def stop_bot() -> None:
    global _bot, _bot_task
    if _bot:
        await _bot.close()
    if _bot_task:
        _bot_task.cancel()
