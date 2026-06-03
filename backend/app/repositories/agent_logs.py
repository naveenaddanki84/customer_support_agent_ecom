"""Per-turn reasoning-log data access (powers the admin dashboard)."""

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import db_manager


def _parse_trace(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value or []


class AgentLogsRepo:
    async def record_turn(
        self,
        session_id,
        user_message: str,
        handling_agent: Optional[str],
        router_intent: Optional[str],
        router_reasoning: Optional[str],
        refund_decision: Optional[str],
        guardrails_score,
        tool_trace: List[Dict[str, Any]],
        final_response: str,
    ) -> None:
        await db_manager.execute_command(
            """
            INSERT INTO agent_logs (
                session_id, user_message, handling_agent, router_intent,
                router_reasoning, refund_decision, guardrails_score,
                tool_trace, final_response
            ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
            """,
            str(session_id), user_message, handling_agent, router_intent,
            router_reasoning, refund_decision,
            Decimal(str(guardrails_score)) if guardrails_score is not None else None,
            json.dumps(tool_trace or []), final_response,
        )

    async def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            """
            SELECT id, session_id, user_message, handling_agent, router_intent,
                   router_reasoning, refund_decision, guardrails_score,
                   tool_trace, final_response, created_at
            FROM agent_logs ORDER BY created_at DESC LIMIT $1
            """,
            limit,
        )
        for row in rows:
            row["tool_trace"] = _parse_trace(row.get("tool_trace"))
        return rows

    async def list_by_session(self, session_id: UUID) -> List[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            """
            SELECT id, user_message, handling_agent, router_intent, router_reasoning,
                   refund_decision, guardrails_score, tool_trace, final_response, created_at
            FROM agent_logs WHERE session_id = $1 ORDER BY created_at ASC
            """,
            session_id,
        )
        for row in rows:
            row["tool_trace"] = _parse_trace(row.get("tool_trace"))
        return rows


agent_logs_repo = AgentLogsRepo()
