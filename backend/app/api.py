"""
REST API endpoints for session management and basic operations.
Minimal implementation focusing on essential functionality.
"""

import logging
from typing import List
from uuid import UUID, uuid4
from datetime import datetime
import json

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.database import db_manager
from app.models import SessionCreate, SessionResponse, ChatMessage
from app.websocket import push_to_session

logger = logging.getLogger(__name__)

# API Router
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/sessions", response_model=SessionResponse)
async def create_session(session_data: SessionCreate) -> SessionResponse:
    """Create a new chat session."""
    try:
        # Convert metadata to JSON string for storage
        metadata_json = json.dumps(session_data.metadata)
        
        # First, insert the session
        insert_query = """
            INSERT INTO sessions (user_id, metadata)
            VALUES ($1, $2::jsonb)
            RETURNING id, user_id, status, created_at, metadata::text
        """
        result = await db_manager.execute_query(
            insert_query, 
            session_data.user_id, 
            metadata_json
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create session")
            
        # Convert the metadata back to a dictionary
        session_row = result[0]
        metadata_dict = json.loads(session_row['metadata'])
        
        # Create the response
        return SessionResponse(
            id=session_row['id'],
            user_id=session_row['user_id'],
            status=session_row['status'],
            created_at=session_row['created_at'],
            metadata=metadata_dict
        )
            
    except Exception as e:
        logger.error(f"Failed to create session: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID) -> SessionResponse:
    """Get session details."""
    try:
        query = """
            SELECT id, user_id, status, created_at, metadata
            FROM sessions
            WHERE id = $1
        """
        result = await db_manager.execute_query(query, session_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = result[0]
        return SessionResponse(
            id=session["id"],
            user_id=session["user_id"],
            status=session["status"],
            created_at=session["created_at"],
            metadata=session["metadata"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: UUID, limit: int = 50) -> List[dict]:
    """Get messages for a session."""
    try:
        query = """
            SELECT id, session_id, sender, content, message_type, created_at, metadata
            FROM messages
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        result = await db_manager.execute_query(query, session_id, limit)
        return result[::-1]  # Return in chronological order
    
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/sessions/{session_id}")
async def close_session(session_id: UUID) -> dict:
    """Close a chat session."""
    try:
        query = """
            UPDATE sessions
            SET status = 'closed', updated_at = NOW()
            WHERE id = $1
            RETURNING id
        """
        result = await db_manager.execute_query(query, session_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"message": "Session closed successfully", "session_id": str(session_id)}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# --- Admin dashboard endpoints -------------------------------------------

@router.get("/admin/logs")
async def get_agent_logs(limit: int = 100) -> List[dict]:
    """Return recent per-turn agent reasoning logs (newest first)."""
    try:
        query = """
            SELECT id, session_id, user_message, handling_agent, router_intent,
                   router_reasoning, refund_decision, guardrails_score,
                   tool_trace, final_response, created_at
            FROM agent_logs
            ORDER BY created_at DESC
            LIMIT $1
        """
        result = await db_manager.execute_query(query, limit)
        # asyncpg returns JSONB columns as strings; parse tool_trace into objects.
        for row in result:
            trace = row.get("tool_trace")
            if isinstance(trace, str):
                try:
                    row["tool_trace"] = json.loads(trace)
                except json.JSONDecodeError:
                    row["tool_trace"] = []
        return result

    except Exception as e:
        logger.error(f"Failed to get agent logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/refund-decisions")
async def get_refund_decisions(limit: int = 100) -> List[dict]:
    """Return the refund decision audit log (newest first)."""
    try:
        query = """
            SELECT rd.id, rd.order_id, rd.decision, rd.amount, rd.reason,
                   rd.created_at, o.item, c.name AS customer_name
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            ORDER BY rd.created_at DESC
            LIMIT $1
        """
        result = await db_manager.execute_query(query, limit)
        return result

    except Exception as e:
        logger.error(f"Failed to get refund decisions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/prompts")
async def get_prompt_versions() -> List[dict]:
    """List each agent's available prompt versions and the active one."""
    from app.prompts import active_version, available_versions, list_agents

    return [
        {
            "agent": agent,
            "active": active_version(agent),
            "versions": available_versions(agent),
        }
        for agent in list_agents()
    ]


@router.get("/admin/stats")
async def get_admin_stats() -> dict:
    """Return high-level counts for the admin dashboard."""
    try:
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

    except Exception as e:
        logger.error(f"Failed to get admin stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/agent")
async def get_agent_info() -> dict:
    """Return the assistant's name and a welcome message for new chats."""
    from app.config import settings
    name = settings.agent_name
    return {
        "name": name,
        "welcome": (
            f"Hi! I'm {name}, your virtual support assistant. I can help with orders, "
            f"refunds, and general questions. How can I help you today?"
        ),
    }


@router.get("/customers")
async def list_customers() -> List[dict]:
    """List seeded customers for the chat user switcher and admin views."""
    try:
        return await db_manager.execute_query(
            "SELECT id, name, email, tier FROM customers ORDER BY id"
        )
    except Exception as e:
        logger.error(f"Failed to list customers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/sessions")
async def list_admin_sessions(limit: int = 100) -> List[dict]:
    """List recent sessions with turn counts and an escalation flag."""
    try:
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
    except Exception as e:
        logger.error(f"Failed to list admin sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/sessions/{session_id}")
async def get_admin_session(session_id: UUID) -> dict:
    """Return a session's messages and per-turn reasoning logs for the trace view."""
    try:
        messages = await db_manager.execute_query(
            """
            SELECT id, sender, content, message_type, created_at, metadata
            FROM messages WHERE session_id = $1 ORDER BY created_at ASC
            """,
            session_id,
        )
        for m in messages:
            md = m.get("metadata")
            if isinstance(md, str):
                try:
                    m["metadata"] = json.loads(md)
                except json.JSONDecodeError:
                    m["metadata"] = {}
        logs = await db_manager.execute_query(
            """
            SELECT id, user_message, handling_agent, router_intent, router_reasoning,
                   refund_decision, guardrails_score, tool_trace, final_response, created_at
            FROM agent_logs WHERE session_id = $1 ORDER BY created_at ASC
            """,
            session_id,
        )
        for row in logs:
            trace = row.get("tool_trace")
            if isinstance(trace, str):
                try:
                    row["tool_trace"] = json.loads(trace)
                except json.JSONDecodeError:
                    row["tool_trace"] = []
        # Pending escalations for this session — let the admin judge them here.
        escalations = await db_manager.execute_query(
            """
            SELECT id, order_id, amount, reason, created_at
            FROM refund_decisions
            WHERE session_id = $1 AND decision = 'escalated' AND resolution IS NULL
            ORDER BY created_at DESC
            """,
            session_id,
        )
        return {
            "session_id": str(session_id),
            "messages": messages,
            "logs": logs,
            "escalations": escalations,
        }
    except Exception as e:
        logger.error(f"Failed to get admin session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/customers/{customer_id}")
async def get_admin_customer(customer_id: int) -> dict:
    """Return a customer profile with orders, refund history, and sessions."""
    try:
        customers = await db_manager.execute_query(
            "SELECT id, name, email, tier, created_at FROM customers WHERE id = $1",
            customer_id,
        )
        if not customers:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer = customers[0]

        orders = await db_manager.execute_query(
            """SELECT id, item, amount, status, is_final_sale, already_refunded, order_date
               FROM orders WHERE customer_id = $1 ORDER BY order_date DESC""",
            customer_id,
        )
        refunds = await db_manager.execute_query(
            """SELECT rd.id, rd.order_id, rd.decision, rd.amount, rd.reason,
                      rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at
               FROM refund_decisions rd
               JOIN orders o ON o.id = rd.order_id
               WHERE o.customer_id = $1 ORDER BY rd.created_at DESC""",
            customer_id,
        )
        sessions = await db_manager.execute_query(
            """SELECT id, status, created_at, updated_at
               FROM sessions WHERE user_id = $1 ORDER BY updated_at DESC""",
            customer["email"],
        )
        return {"customer": customer, "orders": orders,
                "refund_decisions": refunds, "sessions": sessions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get customer detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str, limit: int = 100) -> List[dict]:
    """List a user's chat sessions (newest first) with a derived title."""
    try:
        rows = await db_manager.execute_query(
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
            LIMIT $2
            """,
            user_id, limit,
        )
        for row in rows:
            title = (row.get("title") or "New chat").strip()
            row["title"] = (title[:48] + "…") if len(title) > 48 else title
        return rows
    except Exception as e:
        logger.error(f"Failed to list user sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/escalations")
async def list_escalations(include_resolved: bool = False) -> List[dict]:
    """List refund decisions that were escalated to a human."""
    try:
        pending_query = """
            SELECT rd.id, rd.order_id, rd.session_id, rd.amount, rd.reason,
                   rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at,
                   o.item, c.name AS customer_name, c.email AS customer_email
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE rd.decision = 'escalated' AND rd.resolution IS NULL
            ORDER BY rd.created_at DESC
            """
        all_query = """
            SELECT rd.id, rd.order_id, rd.session_id, rd.amount, rd.reason,
                   rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at,
                   o.item, c.name AS customer_name, c.email AS customer_email
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE rd.decision = 'escalated'
            ORDER BY rd.created_at DESC
            """
        return await db_manager.execute_query(
            all_query if include_resolved else pending_query
        )
    except Exception as e:
        logger.error(f"Failed to list escalations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _compose_resolution_reply(order_id: str, amount, action: str, admin_reason: str) -> str:
    """Have the named agent compose a customer reply for a resolved escalation."""
    from app.config import settings
    from app.openai_client import openai_client

    name = settings.agent_name
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


@router.post("/admin/escalations/{decision_id}/resolve")
async def resolve_escalation(decision_id: UUID, body: dict) -> dict:
    """Approve or reject an escalated refund using the admin's reason; the agent
    composes a reply that is stored and live-pushed into the customer's session."""
    action = (body or {}).get("action")
    reviewer = ((body or {}).get("reviewer") or "admin")[:255]
    admin_reason = ((body or {}).get("reason") or "").strip()
    if action not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="action must be 'approved' or 'rejected'")
    try:
        rows = await db_manager.execute_query(
            """
            UPDATE refund_decisions
            SET resolution = $2, resolved_by = $3, resolution_note = $4, resolved_at = NOW()
            WHERE id = $1 AND decision = 'escalated' AND resolution IS NULL
            RETURNING id, order_id, session_id, amount
            """,
            decision_id, action, reviewer, admin_reason or None,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Escalated decision not found")
        row = rows[0]

        # An approved escalation grants the refund — mark the order as refunded
        # so the same order cannot be refunded again.
        if action == "approved" and row.get("order_id"):
            await db_manager.execute_command(
                "UPDATE orders SET already_refunded = TRUE WHERE upper(id) = upper($1)",
                row["order_id"],
            )

        note = await _compose_resolution_reply(
            row["order_id"], row.get("amount"), action, admin_reason
        )
        if row.get("session_id"):
            await db_manager.execute_command(
                """INSERT INTO messages (session_id, sender, content, message_type, metadata)
                   VALUES ($1, 'assistant', $2, 'text', $3)""",
                row["session_id"], note,
                json.dumps({"agent": "human", "decision": action, "escalation_resolved": True}),
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve escalation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")