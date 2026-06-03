"""Customer data access."""

from typing import Any, Dict, List, Optional

from app.database import db_manager


class CustomersRepo:
    async def list_all(self) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            "SELECT id, name, email, tier FROM customers ORDER BY id"
        )

    async def get(self, customer_id: int) -> Optional[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            "SELECT id, name, email, tier, created_at FROM customers WHERE id = $1",
            customer_id,
        )
        return rows[0] if rows else None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        rows = await db_manager.execute_query(
            "SELECT id, name, email, tier, created_at FROM customers WHERE lower(email) = lower($1)",
            email.strip(),
        )
        return rows[0] if rows else None


customers_repo = CustomersRepo()
