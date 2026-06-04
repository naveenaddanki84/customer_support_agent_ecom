"""
FAQ Agent for handling common customer questions.
Provides knowledge base responses with dynamic loading.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.openai_client import openai_client
from app.prompts import get_prompt
from app.app_config import app_config
from app import knowledge


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
    
    async def process(self, message: str, context: Dict[str, Any]) -> FAQResponse:
        """Process an FAQ query with the LLM, grounded on the FAQ document."""
        # The FAQs live in an editable markdown document, read fresh each call.
        kb_context = knowledge.read_faqs() or "(no FAQs are configured)"

        history = (context or {}).get("history", "")
        history_block = f"Conversation so far:\n{history}\n\n" if history else ""

        prompt = f"""{self.get_system_prompt()}

Your name is {app_config.agent_name}. When greeting a customer for the first time, briefly introduce yourself as {app_config.agent_name}. If asked your name, say it is {app_config.agent_name}.

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