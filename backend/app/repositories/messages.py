"""Message data access (chat transcript persistence)."""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import db_manager


def _parse_metadata(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


class MessagesRepo:
    async def insert(
        self,
        session_id,
        sender: str,
        content: str,
        message_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        rows = await db_manager.execute_query(
            """
            INSERT INTO messages (session_id, sender, content, message_type, metadata)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            session_id, sender, content, message_type, json.dumps(metadata or {}),
        )
        return rows[0]["id"]

    async def list_by_session(self, session_id: UUID, limit: int = 50) -> List[Dict[str, Any]]:
        """Raw rows in chronological order (used by the REST messages endpoint)."""
        rows = await db_manager.execute_query(
            """
            SELECT id, session_id, sender, content, message_type, created_at, metadata
            FROM messages WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2
            """,
            session_id, limit,
        )
        return rows[::-1]

    async def history(self, session_id: UUID, limit: int = 50) -> List[Dict[str, Any]]:
        """JSON-serialisable transcript for the WebSocket (UUID/datetime/JSONB safe)."""
        rows = await db_manager.execute_query(
            """
            SELECT id, session_id, sender, content, message_type, created_at, metadata
            FROM messages WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2
            """,
            session_id, limit,
        )
        out = []
        for row in reversed(rows):
            created = row.get("created_at")
            out.append({
                "id": str(row["id"]),
                "session_id": str(row["session_id"]),
                "sender": row["sender"],
                "content": row["content"],
                "message_type": row.get("message_type", "text"),
                "created_at": created.isoformat() if created else None,
                "metadata": _parse_metadata(row.get("metadata")),
            })
        return out

    async def list_for_trace(self, session_id: UUID) -> List[Dict[str, Any]]:
        """Messages for the admin trace view, with parsed metadata, oldest first."""
        rows = await db_manager.execute_query(
            """
            SELECT id, sender, content, message_type, created_at, metadata
            FROM messages WHERE session_id = $1 ORDER BY created_at ASC
            """,
            session_id,
        )
        for m in rows:
            m["metadata"] = _parse_metadata(m.get("metadata"))
        return rows


messages_repo = MessagesRepo()
