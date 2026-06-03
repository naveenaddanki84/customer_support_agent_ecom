"""Data-access layer. Each repository owns the SQL for one aggregate.

Business logic (services) and HTTP handlers (routers) depend on these instead
of issuing SQL directly, so queries live in one place and are easy to test.
"""

from app.repositories.agent_logs import agent_logs_repo
from app.repositories.customers import customers_repo
from app.repositories.knowledge_base import knowledge_base_repo
from app.repositories.messages import messages_repo
from app.repositories.orders import orders_repo
from app.repositories.policies import policies_repo
from app.repositories.refunds import refunds_repo
from app.repositories.sessions import sessions_repo

__all__ = [
    "agent_logs_repo",
    "customers_repo",
    "knowledge_base_repo",
    "messages_repo",
    "orders_repo",
    "policies_repo",
    "refunds_repo",
    "sessions_repo",
]
