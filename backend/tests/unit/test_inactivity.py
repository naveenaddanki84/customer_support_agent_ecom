"""Unit tests for the inactivity auto-close. No stack: db_manager is monkeypatched."""

import asyncio

import app.inactivity as inactivity
import app.repositories.sessions as sessions_mod
from app.repositories import sessions_repo


def run(coro):
    return asyncio.run(coro)


def test_close_inactive_query_structure(monkeypatch):
    captured = {}

    async def fake_exec(query, *args):
        captured["query"] = query
        captured["args"] = args
        return [{"id": "s1"}, {"id": "s2"}]  # pretend 2 sessions were closed

    monkeypatch.setattr(sessions_mod.db_manager, "execute_query", fake_exec)
    closed = run(sessions_repo.close_inactive(10))

    assert closed == ["s1", "s2"]  # returns the ids of closed sessions
    q = captured["query"]
    assert "status = 'active'" in q
    assert "make_interval(mins => $1)" in q          # parameterised interval
    assert "decision = 'escalated'" in q and "resolution IS NULL" in q  # escalation exemption
    assert "NOT IN" in q
    assert captured["args"] == (10,)


def test_sweep_once_returns_closed_ids(monkeypatch):
    async def fake_close(minutes):
        return ["a", "b", "c"]

    monkeypatch.setattr(inactivity.sessions_repo, "close_inactive", fake_close)
    # No live connections, so the per-session push is a no-op; just check the ids.
    assert run(inactivity.sweep_once()) == ["a", "b", "c"]
