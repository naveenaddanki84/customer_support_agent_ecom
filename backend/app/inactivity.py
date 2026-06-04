"""Background sweep that auto-closes idle chat sessions.

A session with no message for INACTIVITY_MINUTES is closed automatically, EXCEPT
while it has an unresolved human escalation (those stay open until a specialist
resolves them; the inactivity timer then applies). Runs as a background task for
the lifetime of the app.
"""

import asyncio
import logging

from app.repositories import sessions_repo

logger = logging.getLogger(__name__)

INACTIVITY_MINUTES = 10
SWEEP_INTERVAL_SECONDS = 60


async def sweep_once(minutes: int = INACTIVITY_MINUTES) -> int:
    """Close idle sessions once; returns how many were closed."""
    closed = await sessions_repo.close_inactive(minutes)
    if closed:
        logger.info("Auto-closed %d inactive session(s)", closed)
    return closed


async def sweep_loop(
    interval_seconds: int = SWEEP_INTERVAL_SECONDS,
    minutes: int = INACTIVITY_MINUTES,
) -> None:
    """Run the inactivity sweep until cancelled."""
    while True:
        try:
            await sweep_once(minutes)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - one failure must not kill the loop
            logger.error("Inactivity sweep failed: %s", e)
        await asyncio.sleep(interval_seconds)
