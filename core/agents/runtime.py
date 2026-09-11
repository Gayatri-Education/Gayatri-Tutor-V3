"""Gayatri AI — Agent runtime: context, tool dispatch, agent loop."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.agents.registry import AgentResponse, AgentSpec, ModelUnavailableError, agent_registry

logger = logging.getLogger("gayatri.agents.runtime")


@dataclass
class AgentContext:
    """Context passed to agents during processing."""
    session_id: str
    user_message: str
    history: list[dict] = field(default_factory=list)
    model_tier: str = "local"
    model_override: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolSpec:
    """Specification of a tool registered with ToolRegistry."""
    name: str
    func: Callable
    description: str = ""
    argument_schema: dict[str, type] | None = None
    timeout_s: float = 30.0


class ToolRegistry:
    """Registry of available tools that agents can call."""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str = "",
        argument_schema: dict[str, type] | None = None,
        timeout_s: float = 30.0,
        allow_replace: bool = False,
    ) -> Callable:
        """Decorator to register a tool function. Rejects duplicate registrations unless allow_replace=True."""
        def decorator(func: Callable) -> Callable:
            if name in self._tools and not allow_replace:
                raise ValueError(
                    f"Tool '{name}' is already registered. Set allow_replace=True to explicitly overwrite."
                )
            self._tools[name] = ToolSpec(
                name=name,
                func=func,
                description=description,
                argument_schema=argument_schema,
                timeout_s=timeout_s,
            )
            logger.info(f"Registered tool: {name}")
            return func
        return decorator

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def call(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with validated arguments, path safety, and timeout enforcement."""
        spec = self._tools.get(name)
        if spec is None:
            raise ValueError(f"Tool '{name}' not found. Available: {self.list_tools()}")

        # Validate arguments against schema if defined
        if spec.argument_schema:
            for arg_name, expected_type in spec.argument_schema.items():
                if arg_name in kwargs and not isinstance(kwargs[arg_name], expected_type):
                    raise TypeError(
                        f"Argument '{arg_name}' for tool '{name}' must be of type {expected_type.__name__}, "
                        f"got {type(kwargs[arg_name]).__name__}"
                    )

        # Path traversal guard for file/path arguments (Audit #80)
        from pathlib import Path
        for arg_name, arg_val in kwargs.items():
            if isinstance(arg_val, str) and any(k in arg_name.lower() for k in ("path", "file", "dir")):
                if ".." in Path(arg_val).parts:
                    raise PermissionError(
                        f"Path traversal detected in argument '{arg_name}': parent directory traversal ('..') is strictly prohibited."
                    )

        logger.info(f"Tool call: {name}({kwargs})")

        # Enforce tool execution timeout (Audit #79)
        if spec.timeout_s and spec.timeout_s > 0:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(spec.func, **kwargs)
                return future.result(timeout=spec.timeout_s)
            except concurrent.futures.TimeoutError as exc:
                raise TimeoutError(f"Tool '{name}' execution timed out after {spec.timeout_s}s") from exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return spec.func(**kwargs)


# Global tool registry
tool_registry = ToolRegistry()


class AgentRuntime:
    """Runs agents: selects agent, processes request, handles tool calls."""

    def __init__(self, registry=None, tools=None):
        self.registry = registry or agent_registry
        self.tools = tools or tool_registry
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

        try:
            # 2. Instantiate and run the agent
            agent = self.registry.instantiate(spec.name)

            # 3. Process through agent loop (handle tool calls)
            response = self._agent_loop(agent, spec, context)
            return response
        except ModelUnavailableError as exc:
            logger.warning(f"Agent '{spec.name}' failed: local model is unavailable ({exc})")
            return AgentResponse(
                text=(
                    "The local AI model is not installed or unavailable. "
                    "Please download the model file to enable this agent."
                ),
                agent_name=spec.name,
                status="MODEL_UNAVAILABLE",
                metadata={"error": str(exc), "model_unavailable": True},
            )
        except Exception as exc:
            from core.errors import sanitize_error
            sanitized = sanitize_error(exc, category=f"agent_{spec.name}")
            return AgentResponse(
                text=f"Agent '{spec.name}' encountered an error: {sanitized.user_message} (Reference: {sanitized.diagnostic_id})",
                agent_name=spec.name,
                status="ERROR",
                metadata={"error": sanitized.user_message, "diagnostic_id": sanitized.diagnostic_id},
            )

    def _agent_loop(self, agent, spec: AgentSpec, context: AgentContext) -> AgentResponse:
        """Run the agent, handling tool calls in a loop with safety boundaries."""
        import time
        from core.config import AGENT_TIMEOUT_S

        start_time = time.time()
        step_count = 0

        response = agent.process(context)

        # Handle tool calls if the agent produced them
        while response.tool_calls and step_count < self._max_steps:
            # Enforce total agent turn execution timeout
            if time.time() - start_time > AGENT_TIMEOUT_S:
                logger.warning(f"Agent '{spec.name}' tool loop exceeded timeout of {AGENT_TIMEOUT_S}s")
                break

            step_count += 1
            tool_results = []

            for tc in response.tool_calls:
                tool_name = tc.get("tool", "")
                tool_args = tc.get("args", {})

                # Check if tool exists
                if tool_name not in self.tools.list_tools():
                    logger.warning(f"Agent requested unknown tool '{tool_name}'")
                    tool_results.append({
                        "tool": tool_name,
                        "error": f"Tool '{tool_name}' is not recognized or available.",
                    })
                    continue

                try:
                    result = self.tools.call(tool_name, **tool_args)
                    tool_results.append({"tool": tool_name, "result": str(result)})
                except Exception as exc:
                    # Sanitize error to prevent leaking internal stack trace or paths into model context
                    logger.error(f"Tool {tool_name} failed: {exc}")
                    tool_results.append({
                        "tool": tool_name,
                        "error": f"Tool execution failed: {type(exc).__name__}. Please verify arguments.",
                    })

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
