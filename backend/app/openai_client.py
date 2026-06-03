"""
OpenAI client configuration for LangGraph agents.
Provides structured output generation via the Chat Completions API.
"""

import json
from typing import Any, Dict, List, Type, TypeVar
from pydantic import BaseModel

from openai import AsyncOpenAI

from app.config import settings

T = TypeVar('T', bound=BaseModel)


class OpenAIClient:
    """Minimal OpenAI client with structured output support."""

    def __init__(self):
        """Initialize OpenAI client with API key and default model."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1
    ) -> T:
        """Generate a structured response validated against a Pydantic schema."""
        try:
            completion = await self.client.chat.completions.parse(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                response_format=response_schema,
            )

            message = completion.choices[0].message
            if message.refusal:
                raise RuntimeError(f"Model refused to respond: {message.refusal}")
            if message.parsed is None:
                raise RuntimeError("No structured response generated")

            return message.parsed

        except Exception as e:
            raise RuntimeError(f"OpenAI generation failed: {str(e)}")

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate a simple text response."""
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )

            text = completion.choices[0].message.content
            if not text:
                raise RuntimeError("No response text generated")

            return text

        except Exception as e:
            raise RuntimeError(f"OpenAI text generation failed: {str(e)}")

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Run a single tool-enabled chat turn.

        Returns the assistant message (in OpenAI wire format, suitable for
        appending to history) plus any tool calls the model requested. The
        iteration loop itself is driven by the LangGraph refund graph.
        """
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )

            message = completion.choices[0].message

            tool_calls: List[Dict[str, Any]] = []
            for call in (message.tool_calls or []):
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    {"id": call.id, "name": call.function.name, "arguments": arguments}
                )

            return {
                "assistant_message": message.model_dump(exclude_none=True),
                "content": message.content,
                "tool_calls": tool_calls,
            }

        except Exception as e:
            raise RuntimeError(f"OpenAI tool call failed: {str(e)}")


# Global client instance
openai_client = OpenAIClient()
