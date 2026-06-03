"""Policy-document data access."""

from typing import Optional

from app.database import db_manager


class PoliciesRepo:
    async def get_refund_policy(self) -> Optional[str]:
        rows = await db_manager.execute_query(
            "SELECT content FROM policies WHERE name = 'refund_policy'"
        )
        return rows[0]["content"] if rows else None


policies_repo = PoliciesRepo()
