"""Live-stack tests for the new chat/admin endpoints. Run with the stack up:

    docker compose up -d
    .venv/bin/python backend/tests/test_frontend_endpoints.py
"""
import json
import os
import sys
import urllib.request

API = os.getenv("API_BASE", "http://localhost:8000")
_failures = []


def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=20) as r:
        return r.status, json.load(r)


def post(path, body):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.load(r)


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  -> {detail}"))
    if not cond:
        _failures.append(name)


def test_customers():
    status, data = get("/api/v1/customers")
    check("customers status 200", status == 200, str(status))
    check("customers count == 15", isinstance(data, list) and len(data) == 15, str(len(data)))
    check("customer has name+email", bool(data) and {"id", "name", "email"} <= set(data[0]), str(data[:1]))


def test_user_sessions():
    _, s = post("/api/v1/sessions", {"user_id": "alice.johnson@example.com"})
    status, data = get("/api/v1/users/alice.johnson@example.com/sessions")
    check("user sessions status 200", status == 200, str(status))
    check("user sessions includes new session",
          any(row["id"] == s["id"] for row in data), str(data[:2]))


def test_admin_sessions():
    status, data = get("/api/v1/admin/sessions?limit=50")
    check("admin sessions 200", status == 200, str(status))
    check("admin session shape", not data or {"id", "user_id", "message_count"} <= set(data[0]),
          str(data[:1]))


def test_admin_session_detail():
    _, sessions = get("/api/v1/admin/sessions?limit=1")
    if not sessions:
        check("admin session detail (no sessions yet)", True)
        return
    sid = sessions[0]["id"]
    status, data = get(f"/api/v1/admin/sessions/{sid}")
    check("admin session detail 200", status == 200, str(status))
    check("detail has messages+logs", {"messages", "logs"} <= set(data), str(list(data)))


if __name__ == "__main__":
    test_customers()
    test_user_sessions()
    test_admin_sessions()
    test_admin_session_detail()
    print("\nDONE" + (" — FAILURES: " + ",".join(_failures) if _failures else " — all passed"))
    sys.exit(1 if _failures else 0)
