"""
FAQ Agent for handling common customer questions.
Provides knowledge base responses with dynamic loading.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.openai_client import openai_client
from app.prompts import get_prompt
from app.config import settings
from app.database import db_manager
from app.cache import cache_manager


class FAQResponse(BaseModel):
    """Structured response from FAQ agent."""
    content: str
    confidence: float
    source: Optional[str] = None
    reasoning: Optional[str] = None


class FAQAgent(BaseAgent):
    """FAQ agent for knowledge base queries."""
    
    def __init__(self):
        """Initialize FAQ agent with knowledge base."""
        super().__init__(agent_type="faq")
    
    def get_system_prompt(self) -> str:
        """Return FAQ-specific system prompt (versioned)."""
        return get_prompt("faq")
    
    async def _load_knowledge_base(self) -> Dict[str, Any]:
        """Load FAQ knowledge base from database with caching."""
        try:
            # Try cache first
            cached_data = await cache_manager.get_knowledge_base("faq")
            if cached_data:
                return cached_data
            
            # Load from database
            query = """
                SELECT category, question, answer, keywords
                FROM knowledge_base 
                WHERE is_active = true
                ORDER BY category
            """
            result = await db_manager.execute_query(query)
            
            # Organize by category
            knowledge_base = {}
            for row in result:
                category = row['category']
                if category not in knowledge_base:
                    knowledge_base[category] = []
                
                knowledge_base[category].append({
                    "question": row['question'],
                    "answer": row['answer'],
                    "keywords": row['keywords'] or []
                })
            
            # Cache the result
            await cache_manager.cache_knowledge_base("faq", knowledge_base)
            
            return knowledge_base
            
        except Exception as e:
            # Fallback to static data if database fails
            return {
                "returns": [
                    {
                        "question": "How do I return an item?",
                        "answer": "You can return items within 30 days with original receipt.",
                        "keywords": ["return", "refund", "exchange"]
                    }
                ],
                "shipping": [
                    {
                        "question": "What are shipping options?",
                        "answer": "We offer standard (3-5 days) and express (1-2 days) shipping.",
                        "keywords": ["shipping", "delivery", "tracking"]
                    }
                ]
            }
    
    def _format_knowledge_base(self, knowledge_base: Dict[str, Any]) -> str:
        """Render the knowledge base into a compact text block for grounding."""
        lines = []
        for category, entries in knowledge_base.items():
            for entry in entries:
                lines.append(
                    f"[{category}] Q: {entry['question']} A: {entry['answer']}"
                )
        return "\n".join(lines) if lines else "(knowledge base is empty)"

    async def process(self, message: str, context: Dict[str, Any]) -> FAQResponse:
        """Process an FAQ query with the LLM, grounded on the knowledge base."""
        # Load knowledge base and use it as grounding context for the model
        knowledge_base = await self._load_knowledge_base()
        kb_context = self._format_knowledge_base(knowledge_base)

        history = (context or {}).get("history", "")
        history_block = f"Conversation so far:\n{history}\n\n" if history else ""

        prompt = f"""{self.get_system_prompt()}

Your name is {settings.agent_name}. When greeting a customer for the first time, briefly introduce yourself as {settings.agent_name}. If asked your name, say it is {settings.agent_name}.

Knowledge base (authoritative facts — use these for any policy, price, shipping, or return details):
{kb_context}

{history_block}Customer message: {message}"""

        response = await openai_client.generate_text(prompt, temperature=0.5)

        return FAQResponse(
            content=response.strip(),
            confidence=0.8,
            source=None,
            reasoning="Answered from the knowledge base via the LLM",
        ) 