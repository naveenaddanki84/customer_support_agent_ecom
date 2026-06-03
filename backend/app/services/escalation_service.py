"""Human-in-the-loop escalation resolution.

When an admin approves/rejects an escalated refund, the named agent composes a
reply from the admin's reason, persists it, marks the order refunded (on
approval), and live-pushes the message into the customer's session.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.app_config import app_config
from app.openai_client import openai_client
from app.repositories import messages_repo, orders_repo, refunds_repo
from app.websocket import push_to_session

logger = logging.getLogger(__name__)


async def list_pending(include_resolved: bool = False) -> List[Dict[str, Any]]:
    return await refunds_repo.list_escalations(include_resolved)


async def _compose_reply(order_id: str, amount, action: str, admin_reason: str) -> str:
    """Have the named agent compose a customer reply for a resolved escalation."""
    name = app_config.agent_name
    verb = "approved" if action == "approved" else "could not be approved"
    amount_txt = f" (${amount})" if amount is not None else ""
    prompt = (
        f"You are {name}, a warm, professional e-commerce store support assistant. "
        f"A human specialist has reviewed an escalated refund request and decided it {verb}.\n\n"
        f"Order: {order_id}{amount_txt}\n"
        f"Outcome: {'approved' if action == 'approved' else 'rejected'}\n"
        f"Specialist's reason: {admin_reason or '(no reason provided)'}\n\n"
        f"Write a short, friendly CHAT message (2-4 sentences) to the customer telling them this "
        f"outcome and incorporating the specialist's reason naturally. If approved, reassure them "
        f"the refund will be processed; if rejected, be empathetic and clear. "
        f"This is a live chat, NOT an email: do not add a subject line, do not write 'Dear ...', "
        f"and never use placeholders like [Customer's Name]. Address the customer directly. "
        f"You may sign off with just your name, {name}. Do not invent any details beyond the "
        f"outcome and the reason."
    )
    try:
        return (await openai_client.generate_text(prompt, temperature=0.4)).strip()
    except Exception as e:  # noqa: BLE001 - fall back to a plain note if the LLM fails
        logger.error(f"Resolution reply generation failed: {e}")
        outcome = "approved" if action == "approved" else "could not be approved"
        tail = f" {admin_reason}" if admin_reason else ""
        return f"Update on your refund for order {order_id}: it has been {outcome}.{tail} — {name}"


async def resolve(
    decision_id: UUID, action: str, reviewer: str, reason: str
) -> Optional[Dict[str, Any]]:
    """Resolve an escalation. Returns None if no matching pending escalation."""
    row = await refunds_repo.resolve(decision_id, action, reviewer, reason or None)
    if not row:
        return None

    if action == "approved" and row.get("order_id"):
        await orders_repo.mark_refunded(row["order_id"])

    note = await _compose_reply(row["order_id"], row.get("amount"), action, reason)

    if row.get("session_id"):
        await messages_repo.insert(
            row["session_id"], "assistant", note, "text",
            {"agent": "human", "decision": action, "escalation_resolved": True},
        )
        await push_to_session(str(row["session_id"]), {
            "type": "message",
            "data": {
                "session_id": str(row["session_id"]),
                "sender": "assistant",
                "content": note,
                "message_type": "text",
                "metadata": {"agent": "human", "decision": action},
            },
        })

    return {"id": str(row["id"]), "resolution": action,
            "order_id": row["order_id"], "reply": note}
