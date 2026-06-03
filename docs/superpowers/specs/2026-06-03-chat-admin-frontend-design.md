# Design — Chat & Admin Frontend Expansion

**Date:** 2026-06-03
**Status:** Approved (brainstorming) — pending implementation plan

## Goal

Expand the two existing frontend surfaces of the e-commerce refund agent:

1. **Chat** — add a user switcher (the 15 seeded customers) and per-user chat history with resume.
2. **Admin** — add tabbed navigation, a human-in-the-loop escalation queue (approve/reject), per-session reasoning traces in a dedicated route, and a per-customer view.

This is **additive**: no change to the agent loop, LangGraph orchestration, Postgres checkpointer, or refund decision logic. New work is UI plus read/resolve API endpoints and a few schema columns.

## Decisions (from brainstorming)

- **User model:** selectable users are the **15 seeded customers**. Selecting a customer sets `user_id = customer.email`, which keeps refund ownership coherent (the refund agent verifies ownership by email).
- **Escalation action:** Approve/Reject **records the human decision and finalizes the refund**, **and notifies the customer's chat** (option B).
- **Notification delivery:** **B1 — live push** via an in-memory WebSocket connection registry. If the customer's chat is open, push live; otherwise the message is stored and shown on resume. Single-instance only (acceptable for this app).
- **Admin extra:** **Per-customer view** (orders + refund history + sessions). Filters/search, export, and analytics are out of scope for now.

## Chat

### Layout
`/chat` gains a left **sidebar** beside the existing chat panel:
- **User dropdown** — the 15 seeded customers (label = name, value = email).
- **"+ New chat"** button — creates a new session for the selected user.
- **Chat-history list** — the selected user's past sessions, newest first. Each item shows a derived title (first user message, truncated) and a subtitle (last handling agent / refund decision + relative time). The active session is highlighted.

### Behavior
- Selected customer persists in `localStorage` (`selectedCustomerEmail`).
- New session: `POST /api/v1/sessions` with `user_id = email`.
- Resume: clicking a history item loads its messages (`GET /api/v1/sessions/{id}/messages`) and connects the WebSocket to that `session_id`. Because conversation memory is checkpointed in Postgres (keyed by session), resuming restores full agent context.
- Switching users swaps the history list and starts/loads a session for that user.

### New endpoints
- `GET /api/v1/customers` → `[{id, name, email, tier}]` (for the dropdown and per-customer view).
- `GET /api/v1/users/{user_id}/sessions` → sessions for a `user_id` (email), each with `{id, title, last_agent, last_decision, updated_at, message_count}`. Title/subtitle derived from that session's messages/agent_logs.

## Admin

`/admin` refactors into tabs: **Overview** (existing stats + reasoning logs), **Escalations**, **Sessions**, **Customers**.

### Escalations queue
- `GET /api/v1/admin/escalations` → `refund_decisions` where `decision = 'escalated'` and `resolution` is pending, joined to order + customer (order_id, customer name/email, amount, reason, created_at). Resolved items can be shown greyed/filtered.
- **Approve / Reject** → `POST /api/v1/admin/escalations/{decision_id}/resolve` with `{action: 'approved'|'rejected', reviewer?: string}`. The handler:
  1. Updates the `refund_decisions` row: `resolution = action`, `resolved_by = reviewer`, `resolved_at = now()`.
  2. Writes a notification message into **the session where the escalation occurred** (`refund_decisions.session_id`) — a `messages` row, `sender = 'assistant'`, content like *"A specialist has approved your refund for ORD-1003."*. (`refund_decisions` already carries `session_id`, so the target session is unambiguous.)
  3. If that session has a live WebSocket in the connection registry, pushes the message to it immediately (B1).

### Sessions + per-session trace
- `GET /api/v1/admin/sessions` → recent sessions with `{id, user_id, message_count, has_escalation, last_activity}`.
- "View trace" links to **`/admin/sessions/[id]`** (opens in a new tab): renders the conversation plus, per turn, the router intent, handling agent, refund decision, guardrails score, and the full tool-call trace. Backed by `GET /api/v1/admin/sessions/{session_id}` returning `{messages, logs}` (logs = `agent_logs` rows for that session, chronological).

### Per-customer view
- `GET /api/v1/admin/customers/{id}` → `{customer, orders, refund_decisions, sessions}` for a single customer. Rendered as a profile: order list, refund history (with resolution status), and their sessions (linking to the per-session trace).

## Data model changes

Add to `refund_decisions` (in `init.sql` and applied to the running DB):
- `resolution VARCHAR(20)` — `NULL` until an escalated decision is reviewed, then `'approved'` / `'rejected'`.
- `resolved_by VARCHAR(255)` — reviewer label (free text; no auth in this app).
- `resolved_at TIMESTAMP WITH TIME ZONE`.

No other schema changes. The unused `escalations` table is left as-is (the queue is driven by `refund_decisions`).

## Backend: connection registry (B1)

`websocket.py` maintains a module-level `dict[session_id -> WebSocket]` of active chat connections: register on connect, remove on disconnect. The escalation-resolve handler (in `api.py`) imports a small helper (`push_to_session(session_id, payload)`) that looks up the connection and sends the JSON message if present. Sends are best-effort and never block the HTTP response; a failed/closed socket is ignored (the stored message still surfaces on resume).

## Component boundaries

Frontend (keep files focused, per the 200–400 line guideline):
- `chat/page.tsx` — composition; delegate sidebar to `chat/Sidebar.tsx` (user dropdown + history) and keep the message panel as-is.
- `admin/page.tsx` — tab shell; one component per tab: `admin/OverviewTab.tsx`, `admin/EscalationsTab.tsx`, `admin/SessionsTab.tsx`, `admin/CustomersTab.tsx`.
- `admin/sessions/[id]/page.tsx` — per-session trace route.
- Small data hooks for fetches (e.g. `useCustomers`, `useUserSessions`).

Backend:
- New read endpoints grouped in `api.py` (`/customers`, `/users/{id}/sessions`, `/admin/sessions`, `/admin/sessions/{id}`, `/admin/customers/{id}`, `/admin/escalations`) and the resolve endpoint.
- Registry + `push_to_session` helper in `websocket.py`.

## Error handling
- All new endpoints validate inputs (UUID/email/id) and return appropriate 404/400; failures are logged server-side, never leak internals.
- Frontend fetches handle non-OK responses with a visible error state (no silent failures).
- Notification push is best-effort; storage is the source of truth so a dropped live push degrades gracefully to "seen on resume".

## Testing
- Backend: endpoint tests (customers list, user sessions, admin sessions/trace, customer view, escalation resolve updating `refund_decisions` + writing a message).
- Resolve flow: assert the escalated decision's `resolution` is set and a message row is written to the session; live-push asserted via a connected test WebSocket.
- Frontend: smoke via the existing run/verify path (load `/chat` with a selected user + history, `/admin` tabs, `/admin/sessions/[id]`).

## Out of scope
Auth/login, filters/search, log export, analytics charts, multi-instance live push (Redis pub/sub).
