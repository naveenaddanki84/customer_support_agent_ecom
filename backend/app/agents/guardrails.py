"""
Guardrails Agent for content validation and safety.
Filters inappropriate content and detects hallucinations.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.openai_client import openai_client


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
        """Return Guardrails-specific system prompt."""
        return """You review a customer-service reply before it is sent to the customer.

A reply is SAFE when it is a normal, professional customer-service message. This explicitly includes
legitimate help with passwords, logins, account access, billing, subscriptions, and API keys — these
are routine support topics, not security risks.

A reply is UNSAFE only when it contains hate speech, harassment, instructions for wrongdoing,
leaked secrets or another person's private data, or clearly unprofessional / abusive language."""

    async def process(self, message: str, context: Dict[str, Any]) -> GuardrailsResponse:
        """Validate a candidate reply using an LLM safety judgement."""
        prompt = f"""{self.get_system_prompt()}

Reply to review:
\"\"\"{message}\"\"\"

Conversation context: {context or {}}

Assess the reply and return:
- is_safe: true unless the reply is genuinely harmful or abusive per the rules above
- has_hallucination: true only if it asserts specific facts that appear fabricated
- safety_score: 0.0 (clearly unsafe) to 1.0 (clearly safe and professional)
- reasoning: one short sentence explaining the judgement"""

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
