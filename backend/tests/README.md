# Tests

Deterministic **tests** for the API and pure logic — these verify the plumbing
behaves correctly and are meant to be fast and repeatable. Behavioural LLM
evals live separately in `../evaluation/`.

Run with the stack up (`docker compose up -d`):

```bash
.venv/bin/python backend/tests/test_frontend_endpoints.py
```

| File | Scope |
|------|-------|
| `test_frontend_endpoints.py` | Integration tests for the chat/admin REST endpoints (customers, user sessions, admin sessions/trace, customer detail, escalation list + resolve). |

Good next additions (no live stack needed — pure unit tests):
- `policy_guard.reconcile` / `evaluate_order` — the safety-critical decision logic.
- `app_config` loading + env overrides.
- `workflow._format_history` — conversation history rendering.
