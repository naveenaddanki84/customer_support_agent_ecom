"""Background sweep that auto-closes idle chat sessions.

A session with no message for INACTIVITY_MINUTES is closed automatically, EXCEPT
while it has an unresolved human escalation (those stay open until a specialist
resolves them; the inactivity timer then applies). When a closed session is still
connected, a live "chat closed" notice is pushed so the UI can react. Runs as a
background task for the lifetime of the app.

Both timings are env-overridable for testing:
  INACTIVITY_MINUTES (default 10), SWEEP_INTERVAL_SECONDS (default 60).
"""

import asyncio
import logging
import os

from app.repositories import sessions_repo

logger = logging.getLogger(__name__)

INACTIVITY_MINUTES = int(os.getenv("INACTIVITY_MINUTES", "10"))
SWEEP_INTERVAL_SECONDS = int(os.getenv("SWEEP_INTERVAL_SECONDS", "60"))


async def sweep_once(minutes: int = INACTIVITY_MINUTES) -> list[str]:
    """Close idle sessions once; notify any still-connected clients."""
    closed_ids = await sessions_repo.close_inactive(minutes)
    if closed_ids:
        logger.info("Auto-closed %d inactive session(s)", len(closed_ids))
        # Lazy import avoids an import cycle (websocket imports repositories).
        from app.websocket import push_to_session
        for sid in closed_ids:
            await push_to_session(sid, {
                "type": "session_closed",
                "data": {
                    "session_id": sid,
                    "reason": "inactivity",
                    "message": (
                        f"This chat was closed after {minutes} minutes of "
                        "inactivity. Please start a new chat to continue."
                    ),
                },
            })
    return closed_ids


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
