"""
Router Agent for intent classification and message routing.
Uses OpenAI for intelligent conversation routing decisions.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.agents.base_agent import BaseAgent, AgentResponse
from app.agents.faq import FAQAgent
from app.agents.refund import RefundAgent
from app.agents.escalation import EscalationAgent
from app.agents.guardrails import GuardrailsAgent
from app.prompts import get_prompt


class RoutingDecision(BaseModel):
    """Structured routing decision from Router Agent."""
    intent: str
    confidence: float
    next_agent: str
    reasoning: str


class RouterAgent(BaseAgent):
    """Router agent that classifies user intents and routes conversations."""
    
    def __init__(self):
        """Initialize router agent with specialized agents."""
        super().__init__("router")
        self.faq_agent = FAQAgent()
        self.refund_agent = RefundAgent()
        self.escalation_agent = EscalationAgent()
        self.guardrails_agent = GuardrailsAgent()
    
    def get_system_prompt(self) -> str:
        """Return router-specific system prompt (versioned)."""
        return get_prompt("router")

    async def classify_intent(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """Classify user intent and determine routing decision."""
        # Versioned classification guidance + prior conversation + current message.
        history = (context or {}).get("history", "")
        history_block = f"Conversation so far:\n{history}\n\n" if history else ""
        prompt = (
            f"{self.get_system_prompt()}\n\n"
            f"{history_block}"
            f"User message: {user_message}"
        )

        # Generate structured routing decision
        decision = await self.client.generate_structured(
            prompt=prompt,
            response_schema=RoutingDecision,
            temperature=0.1
        )
        
        return decision
    
    async def route_to_agent(
        self,
        user_message: str,
        context: Dict[str, Any],
        next_agent: str
    ) -> AgentResponse:
        """Route message to appropriate specialized agent."""
        if next_agent == "faq":
            response = await self.faq_agent.process(user_message, context)
            return AgentResponse(
                content=response.content,
                confidence=response.confidence,
                agent_type="faq",
                reasoning=response.reasoning
            )
        elif next_agent == "refund":
            response = await self.refund_agent.process(user_message, context)
            return AgentResponse(
                content=response.content,
                confidence=0.9,  # Refund responses are policy-grounded
                agent_type="refund",
                reasoning=response.reasoning
            )
        elif next_agent == "escalation":
            response = await self.escalation_agent.process(user_message, context)
            return AgentResponse(
                content=response.content,
                confidence=0.9,  # Escalation responses have very high confidence
                agent_type="escalation",
                reasoning=response.reasoning
            )
        else:
            # Fallback to router response
            return await self.process(user_message, context)
    
    async def process(self, message: str, context: Dict[str, Any]) -> AgentResponse:
        """Classify intent, delegate to the chosen agent, and validate the reply.

        Routing is driven entirely by the LLM classification — there is no
        deterministic confidence gate. The graph in workflow.py uses the same
        classify_intent + route mechanism; this method exists for direct use.
        """
        decision = await self.classify_intent(message, context)
        agent_response = await self.route_to_agent(message, context, decision.next_agent)

        # Validate the chosen agent's reply through the guardrails agent.
        guardrails_result = await self.guardrails_agent.process(agent_response.content, context)
        if not guardrails_result.is_safe or guardrails_result.safety_score < 0.5:
            return AgentResponse(
                content="I apologize, but I cannot provide that information. Please contact our support team for assistance.",
                confidence=0.5,
                agent_type="router",
                reasoning=f"Content flagged by guardrails. Safety score: {guardrails_result.safety_score:.2f}",
            )

        return agent_response