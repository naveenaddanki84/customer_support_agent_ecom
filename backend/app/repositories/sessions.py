"""Chat session data access."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import db_manager


class SessionsRepo:
    async def create(self, user_id: str, metadata_json: str) -> Dict[str, Any]:
        rows = await db_manager.execute_query(
            """
            INSERT INTO sessions (user_id, metadata)
            VALUES ($1, $2::jsonb)
            RETURNING id, user_id, status, created_at, metadata::text
            """,
            user_id, metadata_json,
        )
        return rows[0]

    async def get(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            "SELECT id, user_id, status, created_at, metadata FROM sessions WHERE id = $1",
            session_id,
        )
        return rows[0] if rows else None

    async def close(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            """
            UPDATE sessions SET status = 'closed', updated_at = NOW()
            WHERE id = $1 RETURNING id
            """,
            session_id,
        )
        return rows[0] if rows else None

    async def close_inactive(self, minutes: int = 10) -> int:
        """Close active sessions idle for `minutes`, except unresolved escalations.

        Idle = no message in the last `minutes`. Sessions with a pending human
        escalation (a refund_decision with decision='escalated' and no resolution
        yet) are exempt; once resolved, the inactivity timer applies. Returns the
        number of sessions closed.
        """
        rows = await db_manager.execute_query(
            """
            UPDATE sessions s
            SET status = 'closed', updated_at = NOW()
            WHERE s.status = 'active'
              AND COALESCE(
                    (SELECT max(m.created_at) FROM messages m WHERE m.session_id = s.id),
                    s.created_at
                  ) < NOW() - make_interval(mins => $1)
              AND s.id NOT IN (
                    SELECT rd.session_id FROM refund_decisions rd
                    WHERE rd.decision = 'escalated'
                      AND rd.resolution IS NULL
                      AND rd.session_id IS NOT NULL
                  )
            RETURNING s.id
            """,
            minutes,
        )
        return len(rows)

    async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """A user's sessions, newest first, with a derived title + last agent/decision."""
        return await db_manager.execute_query(
            """
            SELECT s.id, s.created_at, s.updated_at, s.status,
                   (SELECT count(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT content FROM messages m WHERE m.session_id = s.id
                      AND m.sender = 'user' ORDER BY m.created_at ASC LIMIT 1) AS title,
                   (SELECT al.handling_agent FROM agent_logs al WHERE al.session_id = s.id
                      ORDER BY al.created_at DESC LIMIT 1) AS last_agent,
                   (SELECT al.refund_decision FROM agent_logs al WHERE al.session_id = s.id
                      ORDER BY al.created_at DESC LIMIT 1) AS last_decision
            FROM sessions s
            WHERE s.user_id = $1
            ORDER BY s.updated_at DESC
            """,
            user_id,
        )

    async def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Recent sessions for the admin view, with counts + escalation flag."""
        return await db_manager.execute_query(
            """
            SELECT s.id, s.user_id, s.status, s.created_at, s.updated_at,
                   (SELECT count(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                   EXISTS (SELECT 1 FROM agent_logs al WHERE al.session_id = s.id
                           AND al.refund_decision = 'escalated') AS has_escalation,
                   (SELECT max(al.created_at) FROM agent_logs al WHERE al.session_id = s.id) AS last_activity
            FROM sessions s
            ORDER BY s.updated_at DESC
            LIMIT $1
            """,
            limit,
        )

    async def list_by_user_basic(self, user_id: str) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            "SELECT id, status, created_at, updated_at FROM sessions WHERE user_id = $1 ORDER BY updated_at DESC",
            user_id,
        )


sessions_repo = SessionsRepo()
