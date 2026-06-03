"""Order data access."""

from typing import Any, Dict, List, Optional

from app.database import db_manager


class OrdersRepo:
    async def list_by_email(self, email: str) -> List[Dict[str, Any]]:
        """Orders for a customer (by email), newest first."""
        return await db_manager.execute_query(
            """
            SELECT o.id, o.item, o.amount, o.status, o.is_final_sale,
                   o.already_refunded, o.order_date
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE lower(c.email) = lower($1)
            ORDER BY o.order_date DESC
            """,
            email.strip(),
        )

    async def list_by_customer_id(self, customer_id: int) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            """
            SELECT id, item, amount, status, is_final_sale, already_refunded, order_date
            FROM orders WHERE customer_id = $1 ORDER BY order_date DESC
            """,
            customer_id,
        )

    async def get_with_customer(self, order_id: str) -> Optional[Dict[str, Any]]:
        """A single order joined to its owning customer's id/email/name."""
        rows = await db_manager.execute_query(
            """
            SELECT o.id, o.customer_id, c.email AS customer_email, c.name AS customer_name,
                   o.item, o.amount, o.status, o.is_final_sale, o.already_refunded, o.order_date
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE upper(o.id) = upper($1)
            """,
            order_id.strip(),
        )
        return rows[0] if rows else None

    async def mark_refunded(self, order_id: str) -> None:
        await db_manager.execute_command(
            "UPDATE orders SET already_refunded = TRUE WHERE upper(id) = upper($1)",
            str(order_id),
        )


orders_repo = OrdersRepo()
