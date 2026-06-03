"""Unit tests for the deterministic refund-policy guard.

Pure logic — no database, no LLM, no live stack. These cover the safety-critical
decision rules and the "only ever stricter" reconciliation.
"""

from app.app_config import app_config
from app.policy_guard import evaluate_order, reconcile

THRESHOLD = app_config.refund_policy.escalation_threshold_usd
WINDOW = app_config.refund_policy.refund_window_days


def order(**overrides):
    base = dict(
        id="ORD-100", amount=100.0, status="delivered",
        is_final_sale=False, already_refunded=False, days_since_order=5,
    )
    base.update(overrides)
    return base


# --- evaluate_order: one rule per test ------------------------------------

def test_clean_order_is_approved():
    assert evaluate_order(order())["decision"] == "approved"


def test_missing_order_is_denied():
    assert evaluate_order(None)["decision"] == "denied"


def test_already_refunded_is_denied():
    assert evaluate_order(order(already_refunded=True))["decision"] == "denied"


def test_final_sale_is_denied():
    assert evaluate_order(order(is_final_sale=True))["decision"] == "denied"


def test_cancelled_is_denied():
    assert evaluate_order(order(status="cancelled"))["decision"] == "denied"


def test_processing_is_denied():
    assert evaluate_order(order(status="processing"))["decision"] == "denied"


def test_shipped_is_refundable():
    assert evaluate_order(order(status="shipped"))["decision"] == "approved"


def test_outside_window_is_denied():
    assert evaluate_order(order(days_since_order=WINDOW + 1))["decision"] == "denied"


def test_inside_window_boundary_is_approved():
    assert evaluate_order(order(days_since_order=WINDOW))["decision"] == "approved"


def test_over_threshold_is_escalated():
    assert evaluate_order(order(amount=THRESHOLD + 1))["decision"] == "escalated"


def test_at_threshold_is_approved():
    assert evaluate_order(order(amount=THRESHOLD))["decision"] == "approved"


# --- reconcile: guard only ever makes the outcome stricter ----------------

def test_reconcile_overrides_unsafe_approval_to_escalate():
    r = reconcile("approved", order(amount=THRESHOLD + 500))
    assert r["decision"] == "escalated" and r["overridden"] is True


def test_reconcile_overrides_unsafe_approval_to_deny():
    r = reconcile("approved", order(already_refunded=True))
    assert r["decision"] == "denied" and r["overridden"] is True


def test_reconcile_keeps_valid_llm_denial():
    # guard says approvable, but the LLM denied (e.g. ownership) -> keep denied
    r = reconcile("denied", order())
    assert r["decision"] == "denied" and r["overridden"] is False


def test_reconcile_passes_through_clean_approval():
    r = reconcile("approved", order())
    assert r["decision"] == "approved" and r["overridden"] is False


def test_reconcile_does_not_downgrade_escalation():
    # LLM escalated, guard would approve -> stay escalated (stricter wins)
    r = reconcile("escalated", order())
    assert r["decision"] == "escalated"
