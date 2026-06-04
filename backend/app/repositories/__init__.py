"""Data-access layer. Each repository owns the SQL for one aggregate.

Business logic (services) and HTTP handlers (routers) depend on these instead
of issuing SQL directly, so queries live in one place and are easy to test.

Note: the refund policy and FAQs are NOT here — they are editable markdown
documents read via ``app.knowledge`` (backend/knowledge/*.md).
"""

from app.repositories.agent_logs import agent_logs_repo
from app.repositories.customers import customers_repo
from app.repositories.messages import messages_repo
from app.repositories.orders import orders_repo
from app.repositories.refunds import refunds_repo
from app.repositories.sessions import sessions_repo

__all__ = [
    "agent_logs_repo",
    "customers_repo",
    "messages_repo",
    "orders_repo",
    "refunds_repo",
    "sessions_repo",
]
