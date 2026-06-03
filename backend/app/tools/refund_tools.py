"""
Refund tools — PostgreSQL-backed functions the refund agent can call.

These are the only way the agent reads CRM/order/policy data or records a
decision. All behaviour comes from the data here, never from hardcoded rules.
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from app.database import db_manager

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Convert asyncpg types (Decimal, date) into JSON-serialisable values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _json_safe(v) for k, v in row.items()}


# --- Tool implementations -------------------------------------------------

async def lookup_customer(email: str) -> Dict[str, Any]:
    """Find a customer by email."""
    rows = await db_manager.execute_query(
        "SELECT id, name, email, tier, created_at FROM customers WHERE lower(email) = lower($1)",
        email.strip(),
    )
    if not rows:
        return {"found": False, "message": f"No customer found with email {email}"}
    return {"found": True, "customer": _row_to_dict(rows[0])}


async def get_order(order_id: str) -> Dict[str, Any]:
    """Fetch a single order with its owning customer's id and email."""
    rows = await db_manager.execute_query(
        """
        SELECT o.id, o.customer_id, c.email AS customer_email, c.name AS customer_name,
               o.item, o.amount, o.status, o.is_final_sale, o.already_refunded, o.order_date
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE upper(o.id) = upper($1)
        """,
        order_id.strip(),
    )
    if not rows:
        return {"found": False, "message": f"No order found with id {order_id}"}
    return {"found": True, "order": _row_to_dict(rows[0])}


async def list_customer_orders(email: str) -> Dict[str, Any]:
    """List all orders belonging to the customer with the given email."""
    rows = await db_manager.execute_query(
        """
        SELECT o.id, o.item, o.amount, o.status, o.is_final_sale,
               o.already_refunded, o.order_date
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE lower(c.email) = lower($1)
        ORDER BY o.order_date DESC
        """,
        email.strip(),
    )
    return {"count": len(rows), "orders": [_row_to_dict(r) for r in rows]}


async def get_refund_policy() -> Dict[str, Any]:
    """Return the authoritative refund policy text."""
    rows = await db_manager.execute_query(
        "SELECT content FROM policies WHERE name = 'refund_policy'"
    )
    if not rows:
        return {"found": False, "message": "Refund policy is not configured"}
    return {"found": True, "policy": rows[0]["content"]}


async def record_refund_decision(
    order_id: str,
    decision: str,
    reason: str,
    amount: Optional[float] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist the agent's refund decision to the audit log."""
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in {"approved", "denied", "escalated"}:
        return {
            "recorded": False,
            "message": "decision must be one of: approved, denied, escalated",
        }

    await db_manager.execute_command(
        """
        INSERT INTO refund_decisions (order_id, session_id, decision, amount, reason)
        VALUES ($1, $2::uuid, $3, $4, $5)
        """,
        order_id.strip() if order_id else None,
        session_id,
        decision_norm,
        Decimal(str(amount)) if amount is not None else None,
        reason,
    )
    return {"recorded": True, "order_id": order_id, "decision": decision_norm}


# --- OpenAI tool specs ----------------------------------------------------

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_customer",
            "description": "Look up a customer profile by email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Fetch a single order by its id (e.g. ORD-1001), including which customer owns it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order id, e.g. ORD-1001"}
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_customer_orders",
            "description": "List all orders belonging to a customer, identified by their email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_refund_policy",
            "description": "Retrieve the authoritative company refund policy text to reason against.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_refund_decision",
            "description": (
                "Record the final refund decision to the audit log. Call this exactly once "
                "after you have gathered the order, verified ownership, and checked the policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["approved", "denied", "escalated"],
                    },
                    "amount": {"type": "number", "description": "Order amount in USD"},
                    "reason": {
                        "type": "string",
                        "description": "Short justification citing the relevant policy rule",
                    },
                },
                "required": ["order_id", "decision", "reason"],
            },
        },
    },
]


# --- Dispatcher -----------------------------------------------------------

_TOOLS = {
    "lookup_customer": lookup_customer,
    "get_order": get_order,
    "list_customer_orders": list_customer_orders,
    "get_refund_policy": get_refund_policy,
    "record_refund_decision": record_refund_decision,
}


async def execute_tool(
    name: str, arguments: Dict[str, Any], session_id: Optional[str] = None
) -> str:
    """Execute a tool by name and return a JSON string result."""
    tool = _TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        # record_refund_decision is the only tool that needs the session context.
        if name == "record_refund_decision":
            result = await tool(session_id=session_id, **arguments)
        else:
            result = await tool(**arguments)
        return json.dumps(result, default=_json_safe)
    except TypeError as e:
        logger.warning("Tool %s called with bad arguments %s: %s", name, arguments, e)
        return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
    except Exception as e:  # noqa: BLE001 - surface tool failures to the model
        logger.error("Tool %s failed: %s", name, e)
        return json.dumps({"error": f"Tool {name} failed: {e}"})
