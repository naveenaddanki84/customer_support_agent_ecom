"""
Refund Agent — decides whether to approve, deny, or escalate e-commerce refunds.

Implemented as a LangGraph tool-calling loop (agent <-> tools). All order and
policy data comes from PostgreSQL via tools; there is no hardcoded rule logic.
The model reasons against the fetched policy and order data, then records its
decision through the record_refund_decision tool.
"""

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel

from langgraph.graph import StateGraph, START, END

from app.openai_client import openai_client
from app.prompts import get_prompt
from app.tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)


class RefundResponse(BaseModel):
    """Structured response from the Refund agent."""
    content: str
    decision: Optional[str] = None
    escalation_needed: bool = False
    reasoning: Optional[str] = None
    trace: List[Dict[str, Any]] = []


class _RefundState(TypedDict):
    """Internal state for the refund tool-calling loop."""
    messages: List[Dict[str, Any]]
    trace: List[Dict[str, Any]]
    session_id: Optional[str]
    nudged: bool


class RefundAgent:
    """Refund agent driven by a LangGraph agent<->tools loop."""

    def __init__(self):
        self.agent_type = "refund"
        self.graph = self._build_graph()

    def get_system_prompt(self) -> str:
        return get_prompt("refund")

    def _build_graph(self):
        """Build the LangGraph tool-calling loop: agent -> (tools -> agent)* -> END."""
        builder = StateGraph(_RefundState)
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", self._tools_node)
        builder.add_node("nudge", self._nudge_node)
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "nudge": "nudge", "end": END},
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("nudge", "agent")
        return builder.compile()

    @staticmethod
    def _order_resolved(trace: List[Dict[str, Any]]) -> bool:
        """True if a valid order was fetched (so a decision is warranted)."""
        for entry in trace:
            if entry["tool"] == "get_order":
                try:
                    if json.loads(entry["result"]).get("found"):
                        return True
                except json.JSONDecodeError:
                    pass
        return False

    @staticmethod
    def _decision_recorded(trace: List[Dict[str, Any]]) -> bool:
        return any(t["tool"] == "record_refund_decision" for t in trace)

    async def _agent_node(self, state: _RefundState) -> Dict[str, Any]:
        """Call the LLM with tools; append its message to the conversation."""
        result = await openai_client.chat_with_tools(state["messages"], TOOL_SPECS)
        return {"messages": state["messages"] + [result["assistant_message"]]}

    def _should_continue(self, state: _RefundState) -> str:
        """Drive the loop: run tools, nudge for a missing decision, else end."""
        last_message = state["messages"][-1]
        if last_message.get("tool_calls"):
            return "tools"
        # If the agent resolved an order but is about to reply without recording
        # a decision, nudge it once to call record_refund_decision.
        trace = state.get("trace", [])
        if (
            not state.get("nudged")
            and self._order_resolved(trace)
            and not self._decision_recorded(trace)
        ):
            return "nudge"
        return "end"

    async def _nudge_node(self, state: _RefundState) -> Dict[str, Any]:
        """Force a missing decision to be recorded before the final reply."""
        nudge = {
            "role": "user",
            "content": (
                "Before your final reply you MUST call record_refund_decision exactly "
                "once with your decision (approved, denied, or escalated), the order id, "
                "the amount, and a reason citing the relevant policy rule."
            ),
        }
        return {"messages": state["messages"] + [nudge], "nudged": True}

    async def _tools_node(self, state: _RefundState) -> Dict[str, Any]:
        """Execute every tool call the model requested and feed results back."""
        last_message = state["messages"][-1]
        messages = list(state["messages"])
        trace = list(state.get("trace", []))

        for call in last_message.get("tool_calls", []):
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            result = await execute_tool(name, args, session_id=state.get("session_id"))
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result}
            )
            trace.append({"tool": name, "args": args, "result": result})

        return {"messages": messages, "trace": trace}

    async def process(self, message: str, context: Dict[str, Any]) -> RefundResponse:
        """Run the refund tool loop for one customer message."""
        session_id = (context or {}).get("session_id")
        today = date.today().isoformat()
        history = (context or {}).get("history", "")
        history_block = f"Conversation so far:\n{history}\n\n" if history else ""

        messages = [
            {
                "role": "system",
                "content": f"{self.get_system_prompt()}\n\nToday's date is {today}.",
            },
            {
                "role": "user",
                "content": f"{history_block}Customer message: {message}",
            },
        ]

        try:
            result = await self.graph.ainvoke(
                {
                    "messages": messages,
                    "trace": [],
                    "session_id": session_id,
                    "nudged": False,
                },
                {"recursion_limit": 15},
            )
        except Exception as e:  # noqa: BLE001 - keep the chat alive on loop failure
            logger.error("Refund graph failed: %s", e)
            return RefundResponse(
                content="I'm sorry, I ran into a problem processing that refund request. Please try again or contact support.",
                reasoning=f"Refund graph error: {e}",
            )

        final_message = result["messages"][-1].get("content") or (
            "Could you share the order id (e.g. ORD-1001) and the email on the order so I can look into it?"
        )
        trace = result.get("trace", [])

        # Extract the recorded decision (if any) from the tool trace.
        decision: Optional[str] = None
        for entry in trace:
            if entry["tool"] == "record_refund_decision":
                try:
                    payload = json.loads(entry["result"])
                    if payload.get("recorded"):
                        decision = payload.get("decision")
                except json.JSONDecodeError:
                    pass

        reasoning = (
            f"Refund decision: {decision}" if decision else "Handled refund inquiry"
        )

        return RefundResponse(
            content=final_message,
            decision=decision,
            escalation_needed=decision == "escalated",
            reasoning=reasoning,
            trace=trace,
        )
