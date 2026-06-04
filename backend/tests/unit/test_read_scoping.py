"""Unit tests for cross-customer read scoping in the refund tools.

The read tools must only ever return the signed-in customer's own data, so a
user (or prompt injection) can't read another customer's orders. No stack: the
repositories are monkeypatched.
"""

import asyncio
import json

import app.tools.refund_tools as rt

OWNER = "owner@example.com"
INTRUDER = "intruder@example.com"
ORDER = {
    "id": "ORD-1", "customer_email": OWNER, "item": "Thing", "amount": 100.0,
    "status": "delivered", "is_final_sale": False, "already_refunded": False,
    "order_date": None,
}


def run(coro):
    return asyncio.run(coro)


def _fake_get_order(monkeypatch):
    async def fake(_order_id):
        return dict(ORDER)
    monkeypatch.setattr(rt.orders_repo, "get_with_customer", fake)


def test_owner_sees_their_order(monkeypatch):
    _fake_get_order(monkeypatch)
    assert run(rt.get_order("ORD-1", authenticated_email=OWNER))["found"] is True


def test_non_owner_is_blocked(monkeypatch):
    _fake_get_order(monkeypatch)
    res = run(rt.get_order("ORD-1", authenticated_email=INTRUDER))
    assert res["found"] is False and "account" in res["message"].lower()


def test_no_identity_is_backward_compatible(monkeypatch):
    _fake_get_order(monkeypatch)
    assert run(rt.get_order("ORD-1"))["found"] is True


def test_lookup_customer_only_self(monkeypatch):
    async def fake_get(email):
        return {"id": 1, "email": email, "name": "X"}
    monkeypatch.setattr(rt.customers_repo, "get_by_email", fake_get)
    assert run(rt.lookup_customer(INTRUDER, authenticated_email=OWNER))["found"] is False
    assert run(rt.lookup_customer(OWNER, authenticated_email=OWNER))["found"] is True


def test_list_orders_forced_to_signed_in_customer(monkeypatch):
    captured = {}

    async def fake_list(email):
        captured["email"] = email
        return []
    monkeypatch.setattr(rt.orders_repo, "list_by_email", fake_list)
    run(rt.list_customer_orders("victim@example.com", authenticated_email=OWNER))
    assert captured["email"] == OWNER  # ignored the requested email; used the signed-in one


def test_execute_tool_threads_identity(monkeypatch):
    _fake_get_order(monkeypatch)
    out = run(rt.execute_tool("get_order", {"order_id": "ORD-1"}, authenticated_email=INTRUDER))
    assert json.loads(out)["found"] is False
