"""Gayatri AI — Agent runtime: context, tool dispatch, agent loop."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.agents.registry import AgentResponse, AgentSpec, agent_registry

logger = logging.getLogger("gayatri.agents.runtime")


@dataclass
class AgentContext:
    """Context passed to agents during processing."""
    session_id: str
    user_message: str
    history: list[dict] = field(default_factory=list)
    model_tier: str = "local"
    metadata: dict = field(default_factory=dict)


class ToolRegistry:
    """Registry of available tools that agents can call."""

    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register(self, name: str):
        """Decorator to register a tool function."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = func
            logger.info(f"Registered tool: {name}")
            return func
        return decorator

    def get(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def call(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with given arguments."""
        func = self._tools.get(name)
        if func is None:
            raise ValueError(f"Tool '{name}' not found. Available: {self.list_tools()}")
        logger.info(f"Tool call: {name}({kwargs})")
        return func(**kwargs)


# Global tool registry
tool_registry = ToolRegistry()


class AgentRuntime:
    """Runs agents: selects agent, processes request, handles tool calls."""

    def __init__(self, registry=None, tools=None):
        self.registry = registry or agent_registry
        self.tools = tools or tool_registry
        self._step_count = 0
        self._max_steps = 12

    def process(self, user_message: str, context: AgentContext, spec: AgentSpec | None = None) -> AgentResponse:
        """Process a user message through the agent pipeline.

        1. Dispatch to the best matching agent (if spec not provided)
        2. Let the agent process (may include tool calls)
        3. Return the response
        """
        if spec is None:
            dispatch = self.registry.dispatch(user_message)
            if dispatch is None:
                # No agent matched — return a default response
                return AgentResponse(
                    text=self._default_response(user_message),
                    agent_name="default",
                )
            spec, confidence = dispatch

        # 2. Instantiate and run the agent
        agent = self.registry.instantiate(spec.name)

        # 3. Process through agent loop (handle tool calls)
        response = self._agent_loop(agent, spec, context)

        return response

    def _agent_loop(self, agent, spec: AgentSpec, context: AgentContext) -> AgentResponse:
        """Run the agent, handling tool calls in a loop."""
        step_count = 0

        response = agent.process(context)

        # Handle tool calls if the agent produced them
        while response.tool_calls and step_count < self._max_steps:
            step_count += 1
            tool_results = []

            for tc in response.tool_calls:
                tool_name = tc.get("tool")
                tool_args = tc.get("args", {})
                try:
                    result = self.tools.call(tool_name, **tool_args)
                    tool_results.append({"tool": tool_name, "result": str(result)})
                except Exception as exc:
                    tool_results.append({"tool": tool_name, "error": str(exc)})
                    logger.error(f"Tool {tool_name} failed: {exc}")

            # Feed tool results back to the agent
            context.metadata["tool_results"] = tool_results
            response = agent.process(context)

        return response

    def _default_response(self, user_message: str) -> str:
        """Default response when no agent matches."""
        return (
            "I understand you're asking about something. I can help you with:\n"
            "• Learning programming — type /tutor or ask a coding question\n"
            "• Practicing skills — type /practice\n"
            "• Code review — type /review with your code\n"
            "• Document analysis — type /doc with a file\n\n"
            "What would you like to explore?"
        )
