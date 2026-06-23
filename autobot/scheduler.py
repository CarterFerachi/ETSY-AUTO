"""APScheduler wiring — runs the pipeline daily at 06:00 UTC."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .pipeline import run_pipeline

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(
            _pipeline_job,
            trigger=CronTrigger(hour=6, minute=0),
            id="daily_pipeline",
            name="Daily trend → design → list pipeline",
            replace_existing=True,
        )
        log.info("Scheduler configured: daily pipeline at 06:00 UTC")
    return _scheduler


async def _pipeline_job() -> None:
    log.info("Scheduled pipeline triggered")
    try:
        await run_pipeline()
    except Exception:
        log.exception("Unhandled error in scheduled pipeline")


def start_scheduler() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        log.info("Scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
