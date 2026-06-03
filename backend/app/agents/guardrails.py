"""
Guardrails Agent for content validation and safety.
Filters inappropriate content and detects hallucinations.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.openai_client import openai_client
from app.prompts import get_prompt


class SafetyAssessment(BaseModel):
    """Structured safety judgement returned by the LLM."""
    is_safe: bool
    has_hallucination: bool
    safety_score: float
    reasoning: str


class GuardrailsResponse(BaseModel):
    """Structured response from Guardrails agent."""
    content: str
    is_safe: bool
    has_hallucination: bool
    safety_score: float
    reasoning: Optional[str] = None


class GuardrailsAgent(BaseAgent):
    """Guardrails agent that uses the LLM to judge response safety."""

    def __init__(self):
        """Initialize Guardrails agent."""
        super().__init__(agent_type="guardrails")

    def get_system_prompt(self) -> str:
        """Return Guardrails-specific system prompt (versioned)."""
        return get_prompt("guardrails")

    async def process(self, message: str, context: Dict[str, Any]) -> GuardrailsResponse:
        """Validate a candidate reply using an LLM safety judgement."""
        prompt = f"""{self.get_system_prompt()}

Reply to review:
\"\"\"{message}\"\"\"

Conversation context: {context or {}}"""

        assessment = await openai_client.generate_structured(
            prompt=prompt,
            response_schema=SafetyAssessment,
            temperature=0.0
        )

        # Pass the original reply through unchanged; callers act on the metrics.
        return GuardrailsResponse(
            content=message,
            is_safe=assessment.is_safe,
            has_hallucination=assessment.has_hallucination,
            safety_score=max(0.0, min(1.0, assessment.safety_score)),
            reasoning=assessment.reasoning
        )
