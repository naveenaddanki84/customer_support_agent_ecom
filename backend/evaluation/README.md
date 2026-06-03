# Evaluation

Behavioural **evals** for the LLM agent — these exercise the *judgement* of the
multi-agent system, not the plumbing. They are non-deterministic (an LLM is in
the loop), measure pass-rates and safety invariants, and run against a live
stack rather than mocks. Keep them separate from `../tests/` (deterministic
integration/unit tests).

Run with the stack up (`docker compose up -d`):

```bash
# 50 scenarios: approvals, denials across every policy rule, escalations,
# 8 prompt-injection vectors, FAQ routing, escalation intents, memory.
# Exits 2 if any injection ever yields an unauthorized approval.
.venv/bin/python backend/evaluation/agent_evals.py

# Adversarial edge cases: topic-jumping, PII/data extraction, over-refunding,
# double-refunding, and DB-state verification.
.venv/bin/python backend/evaluation/edge_cases.py
```

| Suite | What it guards |
|-------|----------------|
| `agent_evals.py` | Routing correctness, refund decisions across all policy rules, prompt-injection resistance, memory. Hard gate: no injection → approval. |
| `edge_cases.py`  | Adversarial behaviour — no cross-customer data leaks, can't extract more than an order is worth, can't double-refund. |

These are the right place to add new behavioural scenarios as the policy or
agents evolve. Wire `agent_evals.py` into CI as a release gate.
