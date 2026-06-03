"""
LangGraph workflow for multi-agent customer chat system.
Complete agent orchestration with conditional routing.
"""

import json
import logging
from decimal import Decimal
from typing import Dict, Any, Literal
from uuid import UUID

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables.config import RunnableConfig

from app.database import db_manager
from app.agents.router import RouterAgent
from app.agents.faq import FAQAgent
from app.agents.refund import RefundAgent
from app.agents.escalation import EscalationAgent
from app.agents.guardrails import GuardrailsAgent

logger = logging.getLogger(__name__)


class AgentState(MessagesState):
    """Extended state for multi-agent workflow."""
    session_id: UUID
    user_id: str
    current_agent: str
    agent_reasoning: str
    escalation_level: int
    context: Dict[str, Any]


class ChatWorkflow:
    """Complete LangGraph workflow with all agents."""
    
    def __init__(self):
        """Initialize workflow with all agents."""
        self.router_agent = RouterAgent()
        self.faq_agent = FAQAgent()
        self.refund_agent = RefundAgent()
        self.escalation_agent = EscalationAgent()
        self.guardrails_agent = GuardrailsAgent()
        self.checkpointer = InMemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build complete state graph with all agents."""
        builder = StateGraph(AgentState)
        
        # Add all agent nodes
        builder.add_node("router", self._router_node)
        builder.add_node("faq", self._faq_node)
        builder.add_node("refund", self._refund_node)
        builder.add_node("escalation", self._escalation_node)
        builder.add_node("guardrails", self._guardrails_node)

        # Add conditional routing from router
        builder.add_conditional_edges(
            "router",
            self._route_to_agent,
            {
                "faq": "faq",
                "refund": "refund",
                "escalation": "escalation"
            }
        )

        # Add guardrails validation for all agent responses
        builder.add_edge("faq", "guardrails")
        builder.add_edge("refund", "guardrails")
        builder.add_edge("escalation", "guardrails")
        
        # All paths end at guardrails validation
        builder.add_edge("guardrails", END)
        
        # Start with router
        builder.add_edge(START, "router")
        
        return builder.compile(checkpointer=self.checkpointer)
    
    async def _router_node(self, state: AgentState) -> Dict[str, Any]:
        """Router node for intent classification."""
        last_message = state["messages"][-1]
        user_message = str(last_message.content)
        
        context = {
            "session_id": str(state["session_id"]),
            "user_id": state["user_id"],
            "escalation_level": state.get("escalation_level", 0)
        }
        
        # Classify intent and determine routing
        decision = await self.router_agent.classify_intent(user_message, context)
        
        return {
            "current_agent": "router",
            "agent_reasoning": decision.reasoning,
            "context": {**context, "routing_decision": decision.dict()}
        }
    
    async def _faq_node(self, state: AgentState) -> Dict[str, Any]:
        """FAQ agent node."""
        last_message = state["messages"][-1]
        user_message = str(last_message.content)
        
        context = state.get("context", {})
        response = await self.faq_agent.process(user_message, context)
        
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "faq",
            "agent_reasoning": response.reasoning or ""
        }
    
    async def _refund_node(self, state: AgentState) -> Dict[str, Any]:
        """Refund agent node — runs the LangGraph tool loop and records its decision."""
        last_message = state["messages"][-1]
        user_message = str(last_message.content)

        context = state.get("context", {})
        response = await self.refund_agent.process(user_message, context)

        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "refund",
            "agent_reasoning": response.reasoning or "",
            "context": {
                **context,
                "refund_decision": response.decision,
                "refund_trace": response.trace,
            },
        }
    
    async def _escalation_node(self, state: AgentState) -> Dict[str, Any]:
        """Escalation agent node."""
        last_message = state["messages"][-1]
        user_message = str(last_message.content)
        
        context = state.get("context", {})
        response = await self.escalation_agent.process(user_message, context)
        
        # Increment escalation level
        current_level = state.get("escalation_level", 0)
        
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "escalation",
            "agent_reasoning": response.reasoning or "",
            "escalation_level": current_level + 1
        }
    
    async def _guardrails_node(self, state: AgentState) -> Dict[str, Any]:
        """Guardrails validation node."""
        # Get the last AI message for validation
        ai_messages = [msg for msg in state["messages"] if isinstance(msg, AIMessage)]
        if not ai_messages:
            return {"messages": [AIMessage(content="No response to validate")]}
        
        last_ai_message = ai_messages[-1]
        content = str(last_ai_message.content)
        context = state.get("context", {})

        # Validate through guardrails
        guardrails_result = await self.guardrails_agent.process(content, context)
        guardrails_ctx = {
            **context,
            "guardrails_score": guardrails_result.safety_score,
            "guardrails_is_safe": guardrails_result.is_safe,
        }

        # If unsafe, replace with safe response - but be less restrictive
        if not guardrails_result.is_safe or guardrails_result.safety_score < 0.2:
            safe_response = "I apologize, but I cannot provide that information. Please contact our support team for assistance."
            return {
                "messages": [AIMessage(content=safe_response)],
                "agent_reasoning": f"Content flagged by guardrails. Safety score: {guardrails_result.safety_score:.2f}",
                "context": guardrails_ctx,
            }

        # If safe, return original response
        return {
            "messages": [AIMessage(content=content)],
            "agent_reasoning": f"Content validated. Safety score: {guardrails_result.safety_score:.2f}",
            "context": guardrails_ctx,
        }
    
    def _route_to_agent(self, state: AgentState) -> str:
        """Determine which agent to route to based on router decision."""
        context = state.get("context", {})
        routing_decision = context.get("routing_decision", {})
        next_agent = routing_decision.get("next_agent", "faq")
        
        return next_agent
    
    async def process_message(
        self,
        message: str,
        session_id: UUID,
        user_id: str
    ) -> Dict[str, Any]:
        """Process message through complete workflow."""
        config = RunnableConfig(configurable={"thread_id": str(session_id)})
        
        input_state = AgentState(
            messages=[HumanMessage(content=message)],
            session_id=session_id,
            user_id=user_id,
            current_agent="",
            agent_reasoning="",
            escalation_level=0,
            context={}
        )
        
        result = await self.graph.ainvoke(input_state, config)

        # Extract final response
        ai_messages = [msg for msg in result["messages"] if isinstance(msg, AIMessage)]
        response_content = ai_messages[-1].content if ai_messages else "No response generated"

        ctx = result.get("context", {})
        await self._log_turn(session_id, message, result, ctx, response_content)

        return {
            "content": response_content,
            "agent": result.get("current_agent", "router"),
            "reasoning": result.get("agent_reasoning", ""),
        }

    async def _log_turn(
        self,
        session_id: UUID,
        user_message: str,
        result: Dict[str, Any],
        ctx: Dict[str, Any],
        response_content: str,
    ) -> None:
        """Persist a per-turn reasoning log for the admin dashboard."""
        routing = ctx.get("routing_decision", {}) or {}
        score = ctx.get("guardrails_score")
        try:
            await db_manager.execute_command(
                """
                INSERT INTO agent_logs (
                    session_id, user_message, handling_agent, router_intent,
                    router_reasoning, refund_decision, guardrails_score,
                    tool_trace, final_response
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                """,
                str(session_id),
                user_message,
                result.get("current_agent"),
                routing.get("intent"),
                routing.get("reasoning"),
                ctx.get("refund_decision"),
                Decimal(str(score)) if score is not None else None,
                json.dumps(ctx.get("refund_trace", [])),
                response_content,
            )
        except Exception as e:  # noqa: BLE001 - logging must never break the chat
            logger.error("Failed to write agent_logs row: %s", e)


# Global workflow instance
chat_workflow = ChatWorkflow() 