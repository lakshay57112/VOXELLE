import asyncio
import logging

from . import config, push, service

log = logging.getLogger("voxelle.scheduler")


async def dispatch(notes: list[service.Note]) -> None:
    for role, title, body, url, tag in notes:
        await asyncio.to_thread(push.send, role, title, body, url, tag)


async def run_forever() -> None:
    """Background loop: every few seconds, advance reminders and send pushes."""
    while True:
        try:
            notes = await asyncio.to_thread(service.tick)
            if notes:
                await dispatch(notes)
        except Exception:  # keep the loop alive no matter what
            log.exception("scheduler tick failed")
        await asyncio.sleep(config.SCHEDULER_TICK_SEC)
