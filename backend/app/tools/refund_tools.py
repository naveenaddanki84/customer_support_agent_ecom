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

from app.repositories import customers_repo, orders_repo, policies_repo, refunds_repo

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
    row = await customers_repo.get_by_email(email)
    if not row:
        return {"found": False, "message": f"No customer found with email {email}"}
    return {"found": True, "customer": _row_to_dict(row)}


async def get_order(order_id: str) -> Dict[str, Any]:
    """Fetch a single order with its owning customer's id and email."""
    row = await orders_repo.get_with_customer(order_id)
    if not row:
        return {"found": False, "message": f"No order found with id {order_id}"}

    order = _row_to_dict(row)
    # Provide the date arithmetic as a fact so the model doesn't have to compute
    # it (LLMs are unreliable at date math). The agent still applies the policy's
    # stated window to this number.
    order_date = row.get("order_date")
    if isinstance(order_date, datetime):
        order_date = order_date.date()
    if isinstance(order_date, date):
        order["days_since_order"] = (date.today() - order_date).days
    return {"found": True, "order": order}


async def list_customer_orders(email: str) -> Dict[str, Any]:
    """List all orders belonging to the customer with the given email."""
    rows = await orders_repo.list_by_email(email)
    return {"count": len(rows), "orders": [_row_to_dict(r) for r in rows]}


async def get_refund_policy() -> Dict[str, Any]:
    """Return the authoritative refund policy text."""
    content = await policies_repo.get_refund_policy()
    if not content:
        return {"found": False, "message": "Refund policy is not configured"}
    return {"found": True, "policy": content}


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

    clean_order_id = order_id.strip() if order_id else None

    decision_id = await refunds_repo.record(
        clean_order_id, session_id, decision_norm, amount, reason
    )
    # The deterministic policy guard (in the refund agent) owns the final outcome
    # and the orders.already_refunded marking, so it can correct this row if the
    # model's decision violates policy.
    return {
        "recorded": True,
        "order_id": order_id,
        "decision": decision_norm,
        "decision_id": decision_id,
    }


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
