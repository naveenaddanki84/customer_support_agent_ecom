"""Refund-decision data access (the audit log + escalation queue)."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import db_manager


class RefundsRepo:
    async def record(
        self,
        order_id: Optional[str],
        session_id: Optional[str],
        decision: str,
        amount: Optional[float],
        reason: str,
    ) -> str:
        rows = await db_manager.execute_query(
            """
            INSERT INTO refund_decisions (order_id, session_id, decision, amount, reason)
            VALUES ($1, $2::uuid, $3, $4, $5)
            RETURNING id
            """,
            order_id, session_id, decision,
            Decimal(str(amount)) if amount is not None else None, reason,
        )
        return str(rows[0]["id"])

    async def update_decision(self, decision_id: str, decision: str, reason: str) -> None:
        await db_manager.execute_command(
            "UPDATE refund_decisions SET decision = $2, reason = $3 WHERE id = $1::uuid",
            decision_id, decision, reason,
        )

    async def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            """
            SELECT rd.id, rd.order_id, rd.decision, rd.amount, rd.reason,
                   rd.created_at, o.item, c.name AS customer_name
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            ORDER BY rd.created_at DESC
            LIMIT $1
            """,
            limit,
        )

    async def list_escalations(self, include_resolved: bool = False) -> List[Dict[str, Any]]:
        where = "rd.decision = 'escalated'"
        if not include_resolved:
            where += " AND rd.resolution IS NULL"
        return await db_manager.execute_query(
            f"""
            SELECT rd.id, rd.order_id, rd.session_id, rd.amount, rd.reason,
                   rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at,
                   o.item, c.name AS customer_name, c.email AS customer_email
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE {where}
            ORDER BY rd.created_at DESC
            """
        )

    async def list_pending_for_session(self, session_id: UUID) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            """
            SELECT id, order_id, amount, reason, created_at
            FROM refund_decisions
            WHERE session_id = $1 AND decision = 'escalated' AND resolution IS NULL
            ORDER BY created_at DESC
            """,
            session_id,
        )

    async def list_by_customer_id(self, customer_id: int) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            """
            SELECT rd.id, rd.order_id, rd.decision, rd.amount, rd.reason,
                   rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at
            FROM refund_decisions rd
            JOIN orders o ON o.id = rd.order_id
            WHERE o.customer_id = $1 ORDER BY rd.created_at DESC
            """,
            customer_id,
        )

    async def resolve(
        self, decision_id: UUID, resolution: str, reviewer: str, note: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            """
            UPDATE refund_decisions
            SET resolution = $2, resolved_by = $3, resolution_note = $4, resolved_at = NOW()
            WHERE id = $1 AND decision = 'escalated' AND resolution IS NULL
            RETURNING id, order_id, session_id, amount
            """,
            decision_id, resolution, reviewer, note,
        )
        return rows[0] if rows else None

    async def decision_counts(self) -> Dict[str, Any]:
        rows = await db_manager.execute_query(
            """
            SELECT
                (SELECT count(*) FROM agent_logs) AS total_turns,
                (SELECT count(*) FROM refund_decisions WHERE decision = 'approved') AS approved,
                (SELECT count(*) FROM refund_decisions WHERE decision = 'denied') AS denied,
                (SELECT count(*) FROM refund_decisions WHERE decision = 'escalated') AS escalated
            """
        )
        return rows[0] if rows else {}


refunds_repo = RefundsRepo()
