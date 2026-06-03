"""Admin read-models that aggregate several repositories."""

from typing import Any, Dict, Optional
from uuid import UUID

from app.repositories import (
    agent_logs_repo,
    customers_repo,
    messages_repo,
    orders_repo,
    refunds_repo,
    sessions_repo,
)


async def session_trace(session_id: UUID) -> Dict[str, Any]:
    """A session's conversation, per-turn reasoning, and pending escalations."""
    return {
        "session_id": str(session_id),
        "messages": await messages_repo.list_for_trace(session_id),
        "logs": await agent_logs_repo.list_by_session(session_id),
        "escalations": await refunds_repo.list_pending_for_session(session_id),
    }


async def customer_detail(customer_id: int) -> Optional[Dict[str, Any]]:
    """A customer profile with orders, refund history, and sessions."""
    customer = await customers_repo.get(customer_id)
    if not customer:
        return None
    return {
        "customer": customer,
        "orders": await orders_repo.list_by_customer_id(customer_id),
        "refund_decisions": await refunds_repo.list_by_customer_id(customer_id),
        "sessions": await sessions_repo.list_by_user_basic(customer["email"]),
    }
