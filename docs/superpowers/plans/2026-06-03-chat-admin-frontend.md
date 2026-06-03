# Chat & Admin Frontend Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a customer switcher + per-user chat history to the chat UI, and add tabbed admin navigation with a human-in-the-loop escalation queue, per-session reasoning traces, and a per-customer view.

**Architecture:** Additive only — no change to the LangGraph agent loop, Postgres checkpointer, or refund logic. New read/resolve REST endpoints in FastAPI, three new columns on `refund_decisions`, an in-memory WebSocket connection registry for live notifications, and new/refactored Next.js (React 19, Tailwind v4) components.

**Tech Stack:** FastAPI + asyncpg (Postgres), Next.js 15 / React 19 / Tailwind v4, WebSocket chat. Backend auto-reloads on file change (bind mount). Tests hit the live stack (`docker compose up`) over HTTP/WS, matching the existing `backend/tests/agent_evals.py` pattern.

**Conventions:**
- Run the stack with `docker compose up -d`. Backend hot-reloads on edits to `./backend`.
- Run Python test scripts with the repo venv: `.venv/bin/python backend/tests/<file>.py`.
- Wait helper after a backend edit: `until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done`.
- Commit after each task. Conventional commit messages (`feat:`, `test:`, `chore:`). Attribution disabled.

---

## File Structure

**Backend (modify):**
- `backend/scripts/init.sql` — add `resolution`, `resolved_by`, `resolved_at` to `refund_decisions`.
- `backend/app/api.py` — new endpoints: `/customers`, `/users/{user_id}/sessions`, `/admin/sessions`, `/admin/sessions/{session_id}`, `/admin/customers/{id}`, `/admin/escalations`, `POST /admin/escalations/{decision_id}/resolve`.
- `backend/app/websocket.py` — connection registry + `push_to_session()` + register/unregister on connect/disconnect; broaden the `_serialize_message` reuse.

**Backend (create):**
- `backend/tests/test_frontend_endpoints.py` — live-stack endpoint tests.

**Frontend (create):**
- `frontend/app/lib/api.ts` — typed fetch helpers + shared types.
- `frontend/app/chat/Sidebar.tsx` — user switcher + history.
- `frontend/app/admin/OverviewTab.tsx`, `EscalationsTab.tsx`, `SessionsTab.tsx`, `CustomersTab.tsx`.
- `frontend/app/admin/sessions/[id]/page.tsx` — per-session trace route.

**Frontend (modify):**
- `frontend/app/chat/page.tsx` — render sidebar, manage selected customer + active session.
- `frontend/app/hooks/useChat.ts` — already supports a passed `sessionId`; no change expected (verify).
- `frontend/app/admin/page.tsx` — convert to tab shell.

---

## Task 1: Schema — resolution columns on `refund_decisions`

**Files:**
- Modify: `backend/scripts/init.sql`
- Apply to running DB via `psql`

- [ ] **Step 1: Add columns in init.sql**

In `backend/scripts/init.sql`, find the `CREATE TABLE refund_decisions (...)` block and replace it with:

```sql
CREATE TABLE refund_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id VARCHAR(20) REFERENCES orders(id) ON DELETE SET NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('approved', 'denied', 'escalated')),
    amount NUMERIC(10, 2),
    reason TEXT NOT NULL,
    resolution VARCHAR(20) CHECK (resolution IN ('approved', 'rejected')),
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

- [ ] **Step 2: Apply to the running database (no volume wipe)**

Run:
```bash
docker compose exec -T postgres psql -U user -d db -c "ALTER TABLE refund_decisions ADD COLUMN IF NOT EXISTS resolution VARCHAR(20) CHECK (resolution IN ('approved','rejected')), ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255), ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;"
```
Expected: `ALTER TABLE`

- [ ] **Step 3: Verify columns exist**

Run:
```bash
docker compose exec -T postgres psql -U user -d db -c "\d refund_decisions" | grep -E "resolution|resolved_by|resolved_at"
```
Expected: three rows listing the new columns.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/init.sql
git commit -m "feat: add resolution columns to refund_decisions"
```

---

## Task 2: Backend — `GET /customers` and `GET /users/{user_id}/sessions`

**Files:**
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_frontend_endpoints.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_frontend_endpoints.py`:

```python
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
    # create a session for a known user_id, then list it
    _, s = post("/api/v1/sessions", {"user_id": "alice.johnson@example.com"})
    status, data = get("/api/v1/users/alice.johnson@example.com/sessions")
    check("user sessions status 200", status == 200, str(status))
    check("user sessions includes new session",
          any(row["id"] == s["id"] for row in data), str(data[:2]))


if __name__ == "__main__":
    test_customers()
    test_user_sessions()
    print("\nDONE" + (" — FAILURES: " + ",".join(_failures) if _failures else " — all passed"))
    sys.exit(1 if _failures else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python backend/tests/test_frontend_endpoints.py`
Expected: `test_customers` raises HTTP 404 (endpoint missing) — script errors/fails.

- [ ] **Step 3: Implement the endpoints**

In `backend/app/api.py`, add after the existing `/admin/stats` endpoint (before end of file):

```python
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


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(user_id: str) -> List[dict]:
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
            """,
            user_id,
        )
        for row in rows:
            title = (row.get("title") or "New chat").strip()
            row["title"] = (title[:48] + "…") if len(title) > 48 else title
        return rows
    except Exception as e:
        logger.error(f"Failed to list user sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

- [ ] **Step 4: Wait for reload, run test to verify it passes**

Run:
```bash
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
.venv/bin/python backend/tests/test_frontend_endpoints.py
```
Expected: `customers` and `user sessions` checks PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api.py backend/tests/test_frontend_endpoints.py
git commit -m "feat: add /customers and /users/{id}/sessions endpoints"
```

---

## Task 3: Backend — admin sessions list + per-session trace

**Files:**
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_frontend_endpoints.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_frontend_endpoints.py` (above the `__main__` block) and add calls in `__main__`:

```python
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
```

Add to `__main__` before the DONE print:
```python
    test_admin_sessions()
    test_admin_session_detail()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python backend/tests/test_frontend_endpoints.py`
Expected: the two new checks FAIL (404).

- [ ] **Step 3: Implement endpoints**

In `backend/app/api.py`, add:

```python
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
        return {"session_id": str(session_id), "messages": messages, "logs": logs}
    except Exception as e:
        logger.error(f"Failed to get admin session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

- [ ] **Step 4: Wait for reload, run tests**

Run:
```bash
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
.venv/bin/python backend/tests/test_frontend_endpoints.py
```
Expected: admin sessions + detail checks PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api.py backend/tests/test_frontend_endpoints.py
git commit -m "feat: add admin sessions list + per-session trace endpoints"
```

---

## Task 4: Backend — per-customer detail endpoint

**Files:**
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_frontend_endpoints.py`

- [ ] **Step 1: Add failing test**

Append to the test file and call it in `__main__`:

```python
def test_admin_customer_detail():
    status, data = get("/api/v1/admin/customers/1")
    check("customer detail 200", status == 200, str(status))
    check("customer detail shape", {"customer", "orders", "refund_decisions", "sessions"} <= set(data),
          str(list(data)))
    check("customer has orders", isinstance(data["orders"], list) and len(data["orders"]) >= 1,
          str(len(data.get("orders", []))))
```
Add `test_admin_customer_detail()` to `__main__`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python backend/tests/test_frontend_endpoints.py`
Expected: customer detail checks FAIL (404).

- [ ] **Step 3: Implement endpoint**

In `backend/app/api.py`, add:

```python
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
```

- [ ] **Step 4: Wait for reload, run tests**

Run:
```bash
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
.venv/bin/python backend/tests/test_frontend_endpoints.py
```
Expected: customer detail checks PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api.py backend/tests/test_frontend_endpoints.py
git commit -m "feat: add admin customer detail endpoint"
```

---

## Task 5: Backend — WebSocket connection registry + `push_to_session`

**Files:**
- Modify: `backend/app/websocket.py`

- [ ] **Step 1: Add the registry and helper**

At the top of `backend/app/websocket.py`, after the imports and `logger` definition, add:

```python
# Active chat WebSocket connections, keyed by session id (string).
# Single-process registry — used to live-push admin notifications into a chat.
_active_connections: dict[str, "WebSocket"] = {}


async def push_to_session(session_id: str, payload: dict) -> bool:
    """Send a JSON payload to a session's live WebSocket if connected.

    Best-effort: returns True if a live socket received it, False otherwise.
    The message should already be persisted by the caller; this is only the
    real-time delivery.
    """
    ws = _active_connections.get(str(session_id))
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(payload))
        return True
    except Exception as e:  # noqa: BLE001 - a dead socket just means no live delivery
        logger.warning(f"push_to_session failed for {session_id}: {e}")
        return False
```

- [ ] **Step 2: Register/unregister around the connection lifecycle**

In `handle_websocket_connection`, register right after `await websocket.accept()` and the connect log line:

```python
    _active_connections[str(session_id)] = websocket
```

Find the `finally` block (or the disconnect handling at the end of `handle_websocket_connection`) and ensure it removes the entry. If there is a `finally:` clause, add inside it:

```python
        _active_connections.pop(str(session_id), None)
```
If there is no `finally`, wrap the existing message loop so cleanup always runs:
```python
    try:
        ... existing body (connection confirmation, history, message loop) ...
    finally:
        _active_connections.pop(str(session_id), None)
        logger.info(f"WebSocket connection closed for session {session_id}")
```

- [ ] **Step 3: Verify it imports and the stack stays healthy**

Run:
```bash
python3 -m py_compile backend/app/websocket.py && echo OK
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
echo "backend healthy"
```
Expected: `OK` then `backend healthy`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/websocket.py
git commit -m "feat: add in-memory WS connection registry + push_to_session"
```

---

## Task 6: Backend — escalations list + resolve (with live push)

**Files:**
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_frontend_endpoints.py`

- [ ] **Step 1: Add failing tests**

Append to the test file and call in `__main__`:

```python
import asyncio
import websockets  # noqa: E402

WS = API.replace("http", "ws", 1)


def test_escalations_list_and_resolve():
    # Find an escalated decision (create one if needed by asking for a >$500 refund).
    status, esc = get("/api/v1/admin/escalations")
    check("escalations 200", status == 200, str(status))
    if not esc:
        # drive one escalation through chat
        _, s = post("/api/v1/sessions", {"user_id": "bob.smith@example.com"})
        asyncio.run(_chat(s["id"], "Refund ORD-1003, my email is bob.smith@example.com."))
        _, esc = get("/api/v1/admin/escalations")
    check("at least one escalation", len(esc) >= 1, str(len(esc)))
    if not esc:
        return
    item = esc[0]
    check("escalation shape", {"id", "order_id", "amount", "reason"} <= set(item), str(list(item)))
    status, res = post(f"/api/v1/admin/escalations/{item['id']}/resolve",
                       {"action": "approved", "reviewer": "tester"})
    check("resolve 200", status == 200, str(status))
    check("resolve marks resolution", res.get("resolution") == "approved", str(res))


async def _chat(sid, text):
    async with websockets.connect(f"{WS}/ws/{sid}", open_timeout=15) as ws:
        await ws.send(json.dumps({"type": "chat", "data": {"content": text}}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            d = m.get("data") or {}
            if m.get("type") == "message" and d.get("sender") == "assistant":
                return
```
Add `test_escalations_list_and_resolve()` to `__main__`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python backend/tests/test_frontend_endpoints.py`
Expected: escalations checks FAIL (404 on list/resolve).

- [ ] **Step 3: Implement the endpoints**

In `backend/app/api.py`, add an import near the top (with the other `from app...` imports):

```python
from app.websocket import push_to_session
```

Then add the endpoints:

```python
@router.get("/admin/escalations")
async def list_escalations(include_resolved: bool = False) -> List[dict]:
    """List refund decisions that were escalated to a human."""
    try:
        where = "rd.decision = 'escalated'"
        if not include_resolved:
            where += " AND rd.resolution IS NULL"
        return await db_manager.execute_query(
            f"""
            SELECT rd.id, rd.order_id, rd.session_id, rd.amount, rd.reason,
                   rd.resolution, rd.resolved_by, rd.resolved_at, rd.created_at,
                   o.item, c.name AS customer_name, c.email AS customer_email
            FROM refund_decisions rd
            LEFT JOIN orders o ON o.id = rd.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE {where}
            ORDER BY rd.created_at DESC
            """
        )
    except Exception as e:
        logger.error(f"Failed to list escalations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/escalations/{decision_id}/resolve")
async def resolve_escalation(decision_id: UUID, body: dict) -> dict:
    """Approve or reject an escalated refund; notify the customer's session."""
    action = (body or {}).get("action")
    reviewer = (body or {}).get("reviewer") or "admin"
    if action not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="action must be 'approved' or 'rejected'")
    try:
        rows = await db_manager.execute_query(
            """
            UPDATE refund_decisions
            SET resolution = $2, resolved_by = $3, resolved_at = NOW()
            WHERE id = $1 AND decision = 'escalated'
            RETURNING id, order_id, session_id, amount
            """,
            decision_id, action, reviewer,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Escalated decision not found")
        row = rows[0]

        verb = "approved" if action == "approved" else "declined"
        note = f"A specialist has {verb} your refund request for order {row['order_id']}."
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
        return {"id": str(row["id"]), "resolution": action, "order_id": row["order_id"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve escalation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

> Note: `from app.websocket import push_to_session` — confirm no circular import at startup (websocket.py imports from workflow/models/db, not api). If a circular import appears, import `push_to_session` lazily inside `resolve_escalation` instead.

- [ ] **Step 4: Wait for reload, run tests**

Run:
```bash
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
.venv/bin/python backend/tests/test_frontend_endpoints.py
```
Expected: escalation list + resolve checks PASS. Run the full file; all checks should pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api.py backend/tests/test_frontend_endpoints.py
git commit -m "feat: add escalation queue list + resolve endpoints with live push"
```

---

## Task 7: Frontend — API helpers + shared types

**Files:**
- Create: `frontend/app/lib/api.ts`

- [ ] **Step 1: Create the API module**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Customer { id: number; name: string; email: string; tier: string }
export interface UserSession {
  id: string; title: string; message_count: number
  last_agent: string | null; last_decision: string | null; updated_at: string
}
export interface AdminSession {
  id: string; user_id: string; message_count: number
  has_escalation: boolean; last_activity: string | null; updated_at: string
}
export interface Escalation {
  id: string; order_id: string; session_id: string | null; amount: number | null
  reason: string; customer_name: string | null; customer_email: string | null
  item: string | null; resolution: string | null; created_at: string
}
export interface ToolCall { tool: string; args: Record<string, unknown>; result: string }
export interface AgentLog {
  id: string; user_message: string; handling_agent: string | null
  router_intent: string | null; router_reasoning: string | null
  refund_decision: string | null; guardrails_score: string | null
  tool_trace: ToolCall[]; final_response: string | null; created_at: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return res.json()
}
async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  customers: () => getJson<Customer[]>(`/api/v1/customers`),
  userSessions: (userId: string) =>
    getJson<UserSession[]>(`/api/v1/users/${encodeURIComponent(userId)}/sessions`),
  createSession: (userId: string) =>
    postJson<{ id: string }>(`/api/v1/sessions`, { user_id: userId, metadata: {} }),
  sessionMessages: (id: string) => getJson<unknown[]>(`/api/v1/sessions/${id}/messages`),
  adminSessions: () => getJson<AdminSession[]>(`/api/v1/admin/sessions?limit=100`),
  adminSession: (id: string) =>
    getJson<{ messages: any[]; logs: AgentLog[] }>(`/api/v1/admin/sessions/${id}`),
  adminCustomer: (id: number) => getJson<any>(`/api/v1/admin/customers/${id}`),
  escalations: () => getJson<Escalation[]>(`/api/v1/admin/escalations`),
  resolveEscalation: (id: string, action: 'approved' | 'rejected', reviewer = 'admin') =>
    postJson<{ resolution: string }>(`/api/v1/admin/escalations/${id}/resolve`, { action, reviewer }),
}
```

- [ ] **Step 2: Type-check compiles (build will validate in later tasks)**

Run: `ls frontend/app/lib/api.ts && echo created`
Expected: `created`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/lib/api.ts
git commit -m "feat: add frontend API helpers and shared types"
```

---

## Task 8: Frontend — Chat Sidebar (user switcher + history)

**Files:**
- Create: `frontend/app/chat/Sidebar.tsx`

- [ ] **Step 1: Create the Sidebar component**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { api, Customer, UserSession } from '../lib/api'

interface SidebarProps {
  selectedEmail: string | null
  activeSessionId: string | null
  onSelectUser: (email: string) => void
  onSelectSession: (sessionId: string) => void
  onNewChat: () => void
  refreshKey: number
}

export default function Sidebar({
  selectedEmail, activeSessionId, onSelectUser, onSelectSession, onNewChat, refreshKey,
}: SidebarProps) {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [sessions, setSessions] = useState<UserSession[]>([])

  useEffect(() => {
    api.customers().then(setCustomers).catch(() => setCustomers([]))
  }, [])

  useEffect(() => {
    if (!selectedEmail) { setSessions([]); return }
    api.userSessions(selectedEmail).then(setSessions).catch(() => setSessions([]))
  }, [selectedEmail, refreshKey])

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50">
      <div className="border-b border-gray-200 p-3">
        <div className="text-xs uppercase tracking-wide text-gray-500">Signed in as</div>
        <select
          value={selectedEmail ?? ''}
          onChange={(e) => onSelectUser(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-sm text-gray-800"
        >
          <option value="" disabled>Select a customer…</option>
          {customers.map((c) => (
            <option key={c.id} value={c.email}>{c.name}</option>
          ))}
        </select>
      </div>
      <div className="p-3">
        <button
          onClick={onNewChat}
          disabled={!selectedEmail}
          className="w-full rounded-lg bg-blue-500 px-3 py-2 text-sm text-white hover:bg-blue-600 disabled:opacity-50"
        >
          + New chat
        </button>
      </div>
      <div className="px-3 pb-1 text-xs uppercase tracking-wide text-gray-500">Chat history</div>
      <div className="flex-1 overflow-auto">
        {sessions.length === 0 && (
          <div className="px-3 py-4 text-xs text-gray-400">No chats yet.</div>
        )}
        {sessions.map((s) => {
          const active = s.id === activeSessionId
          return (
            <button
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`block w-full border-l-2 px-3 py-2 text-left text-sm ${
                active ? 'border-blue-500 bg-blue-50' : 'border-transparent hover:bg-gray-100'
              }`}
            >
              <div className="truncate text-gray-800">{s.title}</div>
              <div className="text-xs text-gray-500">
                {[s.last_decision || s.last_agent, new Date(s.updated_at).toLocaleString()]
                  .filter(Boolean).join(' · ')}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/chat/Sidebar.tsx
git commit -m "feat: add chat sidebar (user switcher + history)"
```

---

## Task 9: Frontend — wire Sidebar into the chat page

**Files:**
- Modify: `frontend/app/chat/page.tsx`

- [ ] **Step 1: Read the current chat page**

Run: `sed -n '1,60p' frontend/app/chat/page.tsx` to locate the session bootstrap (around the `useState`/`useEffect` that calls `createSession`).

- [ ] **Step 2: Replace the session bootstrap with user-aware logic**

Goal behavior:
- Read `selectedEmail` from `localStorage` (`selectedCustomerEmail`) on mount.
- When a user is selected, load their sessions; if none active, do NOT auto-create — wait for "+ New chat" or selecting a history item. (Auto-create a first session if the list is empty is acceptable; keep it simple: create on "New chat" and on first user selection if they have no sessions.)
- `onSelectUser(email)`: persist to localStorage, clear `sessionId`, then create a fresh session for them.
- `onNewChat()`: create a new session for `selectedEmail`, set it active, bump `refreshKey`.
- `onSelectSession(id)`: set `sessionId` to that id (the `useChat` hook reconnects automatically), bump `refreshKey`.

Wrap the existing chat panel in a flex row with the sidebar on the left. Concrete edit to the component body (adapt names to the existing file):

```tsx
// near the top of the component
const [selectedEmail, setSelectedEmail] = useState<string | null>(null)
const [refreshKey, setRefreshKey] = useState(0)

useEffect(() => {
  const saved = localStorage.getItem('selectedCustomerEmail')
  if (saved) {
    setSelectedEmail(saved)
    api.createSession(saved).then((s) => setSessionId(s.id))
  }
}, [])

const handleSelectUser = async (email: string) => {
  setSelectedEmail(email)
  localStorage.setItem('selectedCustomerEmail', email)
  const s = await api.createSession(email)
  setSessionId(s.id)
  setRefreshKey((k) => k + 1)
}
const handleNewChat = async () => {
  if (!selectedEmail) return
  const s = await api.createSession(selectedEmail)
  setSessionId(s.id)
  setRefreshKey((k) => k + 1)
}
const handleSelectSession = (id: string) => {
  setSessionId(id)
  setRefreshKey((k) => k + 1)
}
```

Add the import at the top:
```tsx
import Sidebar from './Sidebar'
import { api } from '../lib/api'
```

Wrap the returned JSX so the outermost layout is:
```tsx
<div className="flex h-screen">
  <Sidebar
    selectedEmail={selectedEmail}
    activeSessionId={sessionId}
    onSelectUser={handleSelectUser}
    onSelectSession={handleSelectSession}
    onNewChat={handleNewChat}
    refreshKey={refreshKey}
  />
  <div className="flex-1 overflow-hidden">
    {/* existing chat container JSX unchanged */}
  </div>
</div>
```

Remove the old auto-create `useEffect` that called `createSession(userId)` with a generated id (it is replaced by the localStorage-driven logic above).

- [ ] **Step 3: Verify the chat page builds and loads**

Run:
```bash
until curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/chat | grep -q 200; do sleep 2; done
curl -s http://localhost:3000/chat | grep -c "CssSyntaxError\|Unhandled" || true
docker compose logs frontend --since 30s 2>&1 | grep -iE "compiled|error" | tail -5
```
Expected: page compiles, no CssSyntaxError; `GET /chat 200`.

- [ ] **Step 4: Manual smoke (Playwright or browser)**

Open `http://localhost:3000/chat`. Select "Alice Johnson" → a session starts. Send "hi" → reply appears. Click "+ New chat" → new entry appears in history. Reload → user persists and history lists prior chats.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/chat/page.tsx
git commit -m "feat: wire user switcher + history into chat page"
```

---

## Task 10: Frontend — admin tab shell + Overview tab

**Files:**
- Modify: `frontend/app/admin/page.tsx`
- Create: `frontend/app/admin/OverviewTab.tsx`

- [ ] **Step 1: Extract current dashboard into OverviewTab**

Create `frontend/app/admin/OverviewTab.tsx` and move the existing stats-cards + reasoning-log list rendering from `admin/page.tsx` into it (the `StatCard`, `LogRow`, stats fetch, and logs fetch). Keep it a self-contained client component exporting `default function OverviewTab()`. Reuse `AgentLog` from `../lib/api` for the log type.

- [ ] **Step 2: Convert admin/page.tsx into a tab shell**

```tsx
'use client'

import { useState } from 'react'
import OverviewTab from './OverviewTab'
import EscalationsTab from './EscalationsTab'
import SessionsTab from './SessionsTab'
import CustomersTab from './CustomersTab'

const TABS = ['Overview', 'Escalations', 'Sessions', 'Customers'] as const
type Tab = typeof TABS[number]

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('Overview')
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">Admin Dashboard</h1>
          <p className="text-xs text-gray-500">Agent reasoning, escalations &amp; customers</p>
        </div>
        <a href="/chat" className="text-sm text-blue-600 hover:underline">← Chat</a>
      </header>
      <nav className="flex gap-1 border-b border-gray-200 bg-white px-4">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t ? 'border-b-2 border-blue-500 font-medium text-blue-600' : 'text-gray-500'
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
      <main className="mx-auto max-w-5xl p-6">
        {tab === 'Overview' && <OverviewTab />}
        {tab === 'Escalations' && <EscalationsTab />}
        {tab === 'Sessions' && <SessionsTab />}
        {tab === 'Customers' && <CustomersTab />}
      </main>
    </div>
  )
}
```

> NOTE: `EscalationsTab`, `SessionsTab`, `CustomersTab` are created in Tasks 11–13. To keep this task's build green, create minimal stubs now (each: `export default function X(){return <div className="text-sm text-gray-400">Coming soon</div>}`) and flesh them out in their tasks.

- [ ] **Step 3: Verify build**

Run:
```bash
until curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/admin | grep -q 200; do sleep 2; done
docker compose logs frontend --since 30s 2>&1 | grep -iE "compiled|error" | tail -5
```
Expected: `/admin` compiles; Overview tab shows the existing stats + logs.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/page.tsx frontend/app/admin/OverviewTab.tsx frontend/app/admin/EscalationsTab.tsx frontend/app/admin/SessionsTab.tsx frontend/app/admin/CustomersTab.tsx
git commit -m "feat: admin tab shell + Overview tab (stubs for other tabs)"
```

---

## Task 11: Frontend — Escalations tab (queue + approve/reject)

**Files:**
- Modify: `frontend/app/admin/EscalationsTab.tsx`

- [ ] **Step 1: Implement the queue**

```tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, Escalation } from '../lib/api'

export default function EscalationsTab() {
  const [items, setItems] = useState<Escalation[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.escalations().then(setItems).catch((e) => setError(String(e)))
  }, [])
  useEffect(() => { load() }, [load])

  const resolve = async (id: string, action: 'approved' | 'rejected') => {
    setBusy(id)
    try {
      await api.resolveEscalation(id, action)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {items.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
          No pending escalations. Refunds over $500 will appear here for review.
        </div>
      )}
      <div className="space-y-2">
        {items.map((e) => (
          <div key={e.id} className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4">
            <div className="w-24 font-semibold text-gray-800">{e.order_id}</div>
            <div className="w-40 text-sm text-gray-700">{e.customer_name ?? '—'}</div>
            <div className="w-24 text-sm text-gray-700">
              {e.amount != null ? `$${Number(e.amount).toFixed(2)}` : '—'}
            </div>
            <div className="flex-1 text-sm text-gray-500">{e.reason}</div>
            <div className="flex gap-2">
              <button
                disabled={busy === e.id}
                onClick={() => resolve(e.id, 'approved')}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
              >Approve</button>
              <button
                disabled={busy === e.id}
                onClick={() => resolve(e.id, 'rejected')}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
              >Reject</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify + manual smoke**

Run the backend test to ensure at least one escalation exists, then open `/admin` → Escalations. Approve one and confirm it disappears from the queue.
```bash
.venv/bin/python backend/tests/test_frontend_endpoints.py | grep -i escal
```
Open `http://localhost:3000/admin`, Escalations tab, click Approve on a row → row clears on reload.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/EscalationsTab.tsx
git commit -m "feat: admin escalations queue with approve/reject"
```

---

## Task 12: Frontend — Sessions tab + per-session trace route

**Files:**
- Modify: `frontend/app/admin/SessionsTab.tsx`
- Create: `frontend/app/admin/sessions/[id]/page.tsx`

- [ ] **Step 1: Implement SessionsTab**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { api, AdminSession } from '../lib/api'

export default function SessionsTab() {
  const [sessions, setSessions] = useState<AdminSession[]>([])
  useEffect(() => { api.adminSessions().then(setSessions).catch(() => setSessions([])) }, [])

  return (
    <div className="space-y-2">
      {sessions.map((s) => (
        <div key={s.id} className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-3 text-sm">
          <div className="flex-1 truncate text-gray-800">
            {s.user_id}
            {s.has_escalation && (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">esc</span>
            )}
          </div>
          <div className="w-16 text-gray-500">{s.message_count} msgs</div>
          <div className="w-40 text-gray-400">
            {s.last_activity ? new Date(s.last_activity).toLocaleString() : '—'}
          </div>
          <a
            href={`/admin/sessions/${s.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline"
          >View trace →</a>
        </div>
      ))}
      {sessions.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
          No sessions yet.
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Implement the per-session trace route**

Create `frontend/app/admin/sessions/[id]/page.tsx`:

```tsx
'use client'

import { use, useEffect, useState } from 'react'
import { api, AgentLog } from '../../../lib/api'

function prettyResult(result: string): string {
  try { return JSON.stringify(JSON.parse(result), null, 2) } catch { return result }
}

export default function SessionTracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [logs, setLogs] = useState<AgentLog[]>([])
  const [messages, setMessages] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.adminSession(id)
      .then((d) => { setLogs(d.logs); setMessages(d.messages) })
      .catch((e) => setError(String(e)))
  }, [id])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <a href="/admin" className="text-sm text-blue-600 hover:underline">← Admin</a>
      <h1 className="mb-1 mt-2 text-lg font-bold text-gray-800">Session trace</h1>
      <p className="mb-4 text-xs text-gray-500">{id}</p>
      {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase text-gray-400">Conversation</h2>
          <div className="space-y-2">
            {messages.map((m) => (
              <div key={m.id} className={`rounded-lg p-2 text-sm ${
                m.sender === 'user' ? 'bg-blue-50 text-blue-900' : 'bg-white border border-gray-200 text-gray-800'
              }`}>
                <div className="text-xs text-gray-400">{m.sender}{m.metadata?.agent ? ` · ${m.metadata.agent}` : ''}</div>
                {m.content}
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase text-gray-400">Reasoning per turn</h2>
          <div className="space-y-3">
            {logs.map((log) => (
              <div key={log.id} className="rounded-lg border border-gray-200 bg-white p-3 text-sm">
                <div className="mb-1 flex items-center gap-2">
                  {log.handling_agent && (
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">{log.handling_agent}</span>
                  )}
                  {log.refund_decision && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">{log.refund_decision}</span>
                  )}
                  <span className="truncate text-gray-700">{log.user_message}</span>
                </div>
                <div className="text-xs text-gray-500">intent: {log.router_intent || '—'}</div>
                {log.tool_trace?.length > 0 && (
                  <ol className="mt-2 space-y-1">
                    {log.tool_trace.map((t, i) => (
                      <li key={i} className="rounded bg-gray-50 p-2">
                        <div className="font-mono text-xs font-semibold text-blue-700">
                          {i + 1}. {t.tool}({JSON.stringify(t.args)})
                        </div>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-gray-600">{prettyResult(t.result)}</pre>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify build + manual smoke**

```bash
until curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/admin | grep -q 200; do sleep 2; done
docker compose logs frontend --since 30s 2>&1 | grep -iE "compiled|error" | tail -5
```
Open `/admin` → Sessions → "View trace" opens a new tab with conversation + reasoning.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/SessionsTab.tsx "frontend/app/admin/sessions/[id]/page.tsx"
git commit -m "feat: admin sessions tab + per-session trace route"
```

---

## Task 13: Frontend — Customers tab + detail

**Files:**
- Modify: `frontend/app/admin/CustomersTab.tsx`

- [ ] **Step 1: Implement the customers tab (list + inline detail)**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { api, Customer } from '../lib/api'

export default function CustomersTab() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [detail, setDetail] = useState<any | null>(null)

  useEffect(() => { api.customers().then(setCustomers).catch(() => setCustomers([])) }, [])
  const open = (id: number) => api.adminCustomer(id).then(setDetail).catch(() => setDetail(null))

  return (
    <div className="grid grid-cols-3 gap-6">
      <div className="space-y-1">
        {customers.map((c) => (
          <button
            key={c.id}
            onClick={() => open(c.id)}
            className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${
              detail?.customer?.id === c.id ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-100 text-gray-700'
            }`}
          >
            {c.name} <span className="text-xs text-gray-400">· {c.tier}</span>
          </button>
        ))}
      </div>
      <div className="col-span-2">
        {!detail && <div className="text-sm text-gray-400">Select a customer to view orders, refunds, and sessions.</div>}
        {detail && (
          <div className="space-y-4 text-sm">
            <div>
              <div className="text-lg font-semibold text-gray-800">{detail.customer.name}</div>
              <div className="text-gray-500">{detail.customer.email} · {detail.customer.tier}</div>
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Orders ({detail.orders.length})</div>
              {detail.orders.map((o: any) => (
                <div key={o.id} className="flex justify-between border-b border-gray-100 py-1">
                  <span>{o.id} · {o.item}</span>
                  <span className="text-gray-500">${Number(o.amount).toFixed(2)} · {o.status}
                    {o.is_final_sale ? ' · final sale' : ''}{o.already_refunded ? ' · refunded' : ''}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Refund decisions ({detail.refund_decisions.length})</div>
              {detail.refund_decisions.map((r: any) => (
                <div key={r.id} className="flex justify-between border-b border-gray-100 py-1">
                  <span>{r.order_id} · {r.decision}{r.resolution ? ` → ${r.resolution}` : ''}</span>
                  <span className="text-gray-400">{new Date(r.created_at).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Sessions ({detail.sessions.length})</div>
              {detail.sessions.map((s: any) => (
                <a key={s.id} href={`/admin/sessions/${s.id}`} target="_blank" rel="noopener noreferrer"
                   className="block text-blue-600 hover:underline">{s.id}</a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify + manual smoke**

Open `/admin` → Customers → click "Bob Smith" → orders, refund decisions (with resolution if resolved), and sessions render.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/CustomersTab.tsx
git commit -m "feat: admin customers tab with per-customer detail"
```

---

## Task 14: End-to-end verification + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run all backend endpoint tests**

```bash
until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done
.venv/bin/python backend/tests/test_frontend_endpoints.py
```
Expected: `DONE — all passed`.

- [ ] **Step 2: Full live notification check (B1)**

Manual: open `/chat` as Bob Smith, send "Refund ORD-1003, my email is bob.smith@example.com." (escalates). In another tab open `/admin` → Escalations → Approve that row. Switch back to the chat tab — the message "A specialist has approved your refund request for order ORD-1003." appears live (no reload).

- [ ] **Step 3: Update README**

In `README.md`, under the admin/chat sections, add brief notes: customer switcher + per-user history on `/chat`; admin tabs (Overview/Escalations/Sessions/Customers), the escalation approve/reject queue, and `/admin/sessions/<id>` traces. List the new endpoints in the API section.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document chat switcher/history and admin tabs/escalations"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Self-Review Notes

- **Spec coverage:** user switcher (T8–9), per-user history + resume (T2, T8–9), admin tabs (T10), escalation queue + resolve + live push (T1, T5, T6, T11), per-session trace route (T3, T12), per-customer view (T4, T13), `refund_decisions` resolution columns (T1), connection registry (T5). All spec sections mapped.
- **Type consistency:** `api.ts` types (`Escalation`, `AgentLog`, `AdminSession`, `UserSession`, `Customer`) are reused by every consuming component; endpoint JSON shapes match the SQL `SELECT` column names.
- **Resume semantics:** changing `sessionId` in `chat/page.tsx` triggers the existing `useChat` reconnect; the Postgres checkpointer restores agent memory for that `session_id` (verified earlier in the project).
- **Circular import risk:** `api.py` importing `push_to_session` from `websocket.py` — `websocket.py` does not import `api.py`, so it is safe; fallback is a lazy import inside `resolve_escalation`.
