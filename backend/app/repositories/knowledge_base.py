"""FAQ knowledge-base data access."""

from typing import Any, Dict, List

from app.database import db_manager


class KnowledgeBaseRepo:
    async def list_active(self) -> List[Dict[str, Any]]:
        return await db_manager.execute_query(
            """
            SELECT category, question, answer, keywords
            FROM knowledge_base
            WHERE is_active = true
            ORDER BY category
            """
        )


knowledge_base_repo = KnowledgeBaseRepo()
