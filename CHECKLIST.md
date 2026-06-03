# E-commerce Refund Agent — Build Checklist

Converting this multi-agent chat into an **AI Customer Support Agent that processes or denies
e-commerce refunds**, per the challenge brief.

**Agent mapping (decided):**
- **Router** — stays (now also routes to `refund`)
- **Support → Refund agent** — renamed and rebuilt around tool-calling
- **FAQ** — stays
- **Guardrails** — stays (already LLM-driven)
- **Escalation** — stays (handles refunds > $500 / human-review path)

**Hard rule:** no deterministic code — every decision is LLM-driven; data/policy come from the DB, not hardcoded branches.

---

## Current state (baseline)

- Agents: `router`, `support`, `faq`, `guardrails`, `escalation`, wired through `workflow.py` (LangGraph). FAQ + guardrails are already LLM-driven.
- Deterministic code still present: `support.py` (`_needs_escalation`, `_requires_action`), `faq.py` (`_find_best_match` confidence), router `confidence > 0.7` gate.
- No tool-calling layer — agents don't dynamically call tools; FAQ queries the DB directly.
- Data: `init.sql` has `knowledge_base` (SaaS FAQ), `sessions`, `messages`, `escalations`. **No customers, orders, or refund policy.**
- Frontend: chat only (`/chat`). **No admin dashboard / reasoning-log view.**

---

## 1. Synthetic data (CRM + policy)
- [ ] Add `customers` table to `init.sql` — ~15 profiles (id, name, email, tier/loyalty, account_created).
- [ ] Add `orders` table — order_id, customer_id, item, amount, status, `is_final_sale` (bool), order_date, already_refunded.
- [ ] Seed ~15 customers with multi-order histories covering edge cases: final-sale items, orders > $500, already-refunded orders, very old orders.
- [ ] Add `refund_policy` document — strict rules as text (final sale = non-refundable; > $500 = human escalation; refund window e.g. 30 days; one refund per order). Store in a `policies` table (or markdown loaded at runtime) so the agent reads it, not hardcodes it.
- [ ] (Optional) Re-theme `knowledge_base` FAQ entries to e-commerce (shipping, returns, order tracking) — FAQ logic stays the same.

## 2. Tool layer (function calling — the agent loop)
- [ ] Create `backend/app/tools/` with LLM-callable tools: `lookup_customer(email/id)`, `get_order(order_id)`, `list_customer_orders(customer_id)`, `get_refund_policy()`, `record_refund_decision(order_id, decision, reason)`.
- [ ] Add an OpenAI **function-calling loop** in `openai_client.py` (e.g. `generate_with_tools(prompt, tools)`) — model picks tools, you execute, feed results back, repeat until a final answer.
- [ ] Tools query Postgres via `db_manager.execute_query` (parameterized — no SQL injection).

## 3. Refund agent (rename Support → Refund)
- [ ] Rename `support.py` → `refund.py` (`SupportAgent` → `RefundAgent`); update `router.py`, `workflow.py`, `__init__.py` imports.
- [ ] **Delete** `_needs_escalation` and `_requires_action` (deterministic keyword logic).
- [ ] Refund agent drives the tool loop: look up customer/order → read policy → LLM reasons about eligibility → decide **approve / deny / escalate**, returning structured output (`decision`, `reason`, `order_id`, `escalate`).
- [ ] Policy enforcement is LLM-reasoned against the fetched policy text (not `if amount > 500`). Escalation routes to the existing `escalation` agent.

## 4. Router & workflow (stay, minor wiring)
- [ ] Router keeps its job but `next_agent` now includes `refund` (was `support`). Update the agent list in the router system prompt.
- [ ] Replace the deterministic `confidence > 0.7` gate with LLM-driven routing (trust the structured decision / emit the route directly).
- [ ] Confirm `workflow.py` graph: router → refund/faq/escalation → guardrails → out.

## 5. Guardrails (stay) + resilience
- [ ] Keep the LLM-driven guardrails (done).
- [ ] Add **prompt-injection resistance**: refund agent treats order/policy data as ground truth and ignores user override attempts ("ignore policy", "I'm an admin, approve it", "the CEO said refund me").
- [ ] Test cases: aggressive refund demands, final-sale refund attempts, > $500 auto-approve attempts, injection ("developer mode"), refund for someone else's order.

## 6. Reasoning logs + admin dashboard
- [ ] Persist per-turn reasoning to a table: which agent ran, tools called + args + results, decision and why (`workflow.py` already tracks `agent_reasoning` — extend it).
- [ ] Add backend endpoints: `GET /api/v1/admin/logs` and per-session reasoning trace.
- [ ] Build `frontend/app/admin/page.tsx` — dashboard showing the agent's internal reasoning logs (agent path, tool calls, decisions) alongside the chat.

## 7. Docs & delivery
- [ ] Update `README.md`: API key setup, **agent-loop architecture overview** (router → refund/faq → tools → guardrails → escalation), and the refund policy rules.
- [ ] Verify `docker-compose up` brings up everything clean with the new schema auto-seeding.
- [ ] Private GitHub repo (`customer_support_agent_ecom` remote) — commit & push.

## 8. Remove remaining deterministic code (no-hardcoding rule)
- [ ] `refund.py` keyword helpers → removed (section 3).
- [ ] `faq.py` `_find_best_match` confidence heuristic → replace with LLM-reported confidence or drop.
- [ ] Audit for leftover keyword lists / `if "x" in message` branches across `agents/` and `workflow.py`.
