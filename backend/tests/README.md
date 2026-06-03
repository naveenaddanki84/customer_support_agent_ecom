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

## Unit tests (`tests/unit/`)

Fast, pure-logic tests — **no live stack, no Docker, no DB**. Run from the repo root:

```bash
.venv/bin/python -m pytest backend/tests/unit -q
```

| File | Covers |
|------|--------|
| `test_policy_guard.py` | Every refund-policy rule + the "only ever stricter" reconciliation (the safety-critical guard). |
| `test_app_config.py` | `config.yaml` loading and env overrides. |

Backend deps include `pytest` in the `dev` dependency group (`uv sync` installs it).
