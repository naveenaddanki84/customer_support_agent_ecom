"""
Deterministic refund-policy guard.

A safety net layered over the LLM refund agent. It re-derives the verdict from
the order's own data and the thresholds in ``config.yaml`` and only ever makes
the outcome STRICTER (approved -> escalated -> denied) — never more lenient. This
blocks unauthorized approvals (e.g. an LLM wobble auto-approving a $1,299 order)
while preserving valid LLM denials it does not evaluate, such as ownership.
"""

from typing import Any, Dict, Optional

from app.app_config import app_config

# Outcome severity: a higher rank is stricter.
_RANK = {"approved": 0, "escalated": 1, "denied": 2}


def evaluate_order(order: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Return the deterministic verdict for an order from data + policy config.

    Returns ``{"decision": approved|denied|escalated, "reason": str}``.
    Ownership is intentionally NOT checked here (it needs the claimed identity);
    the LLM handles ownership and this guard backs up the pure data rules.
    """
    pol = app_config.refund_policy
    if not order:
        return {"decision": "denied", "reason": "Order not found."}
    if order.get("already_refunded"):
        return {"decision": "denied", "reason": "This order has already been refunded."}
    if order.get("is_final_sale"):
        return {"decision": "denied", "reason": "Final-sale items are non-refundable."}

    status = str(order.get("status") or "").lower()
    if status == "cancelled":
        return {"decision": "denied", "reason": "Cancelled orders were never charged."}
    if status not in [s.lower() for s in pol.refundable_statuses]:
        return {"decision": "denied", "reason": f"Orders with status '{status}' are not refundable."}

    days = order.get("days_since_order")
    if days is not None and days > pol.refund_window_days:
        return {"decision": "denied",
                "reason": f"Outside the {pol.refund_window_days}-day refund window."}

    amount = float(order.get("amount") or 0)
    if amount > pol.escalation_threshold_usd:
        return {"decision": "escalated",
                "reason": (f"Amount ${amount:.2f} exceeds the "
                           f"${pol.escalation_threshold_usd:.0f} threshold and needs "
                           f"human approval.")}

    return {"decision": "approved", "reason": "Meets all automated refund-policy checks."}


def reconcile(llm_decision: Optional[str], order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine the LLM's decision with the guard, taking the stricter outcome.

    Returns ``{"decision", "guard_reason", "overridden"}``.
    """
    verdict = evaluate_order(order)
    guard = verdict["decision"]
    llm = llm_decision if llm_decision in _RANK else "approved"
    final = guard if _RANK[guard] >= _RANK[llm] else llm
    return {"decision": final, "guard_reason": verdict["reason"], "overridden": final != llm}
