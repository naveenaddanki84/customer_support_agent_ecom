"""
Escalation Agent for human handoff coordination.
Manages transition to human support with context preservation.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.openai_client import openai_client
from app.prompts import get_prompt


class EscalationResponse(BaseModel):
    """Structured response from Escalation agent."""
    content: str
    escalation_reason: str
    priority: str
    context_summary: str
    reasoning: Optional[str] = None


class _EscalationDecision(BaseModel):
    """LLM-produced escalation classification."""
    content: str
    escalation_reason: str
    priority: str


class EscalationAgent(BaseAgent):
    """Escalation agent for human handoff coordination."""

    def __init__(self):
        """Initialize Escalation agent."""
        super().__init__(agent_type="escalation")

    def get_system_prompt(self) -> str:
        """Return Escalation-specific system prompt (versioned)."""
        return get_prompt("escalation")

    async def process(self, message: str, context: Dict[str, Any]) -> EscalationResponse:
        """Process an escalation request and prepare the human handoff."""
        history = (context or {}).get("history", "")
        history_block = f"Conversation so far:\n{history}\n\n" if history else ""

        prompt = f"""{self.get_system_prompt()}

{history_block}Customer message: {message}"""

        decision = await openai_client.generate_structured(
            prompt=prompt,
            response_schema=_EscalationDecision,
            temperature=0.3,
        )

        return EscalationResponse(
            content=decision.content,
            escalation_reason=decision.escalation_reason,
            priority=decision.priority,
            context_summary=self._create_context_summary(context),
            reasoning=f"Escalation processed. Reason: {decision.escalation_reason}, Priority: {decision.priority}",
        )

    def _create_context_summary(self, context: Dict[str, Any]) -> str:
        """Assemble a context summary for the human agent (metadata only)."""
        summary_parts = []

        if "session_id" in context:
            summary_parts.append(f"Session: {context['session_id']}")
        if "user_id" in context:
            summary_parts.append(f"User: {context['user_id']}")
        if "escalation_level" in context:
            summary_parts.append(f"Escalation Level: {context['escalation_level']}")

        return " | ".join(summary_parts) if summary_parts else "No context available"
