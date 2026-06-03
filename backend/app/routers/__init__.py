"""HTTP routers. Thin: validate input, delegate to services/repositories,
shape the response. No SQL, no business logic."""

from app.routers.admin import router as admin_router
from app.routers.chat import router as chat_router

__all__ = ["chat_router", "admin_router"]
