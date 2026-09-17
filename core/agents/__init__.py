"""Gayatri AI — Agents package."""

# Register all default, prompt-engineered, and K-12 agents (idempotent)
from core.agents.default_agents import register_default_agents
from core.agents.prompt_agents import register_prompt_agents
from core.agents.k12_agents import register_k12_agents
from core.agents.registry import AgentResponse, AgentSpec, agent_registry
from core.agents.runtime import AgentContext, AgentRuntime, ToolRegistry, tool_registry

register_default_agents()
register_prompt_agents()
register_k12_agents()

__all__ = [
    "AgentContext",
    "AgentResponse",
    "AgentRuntime",
    "AgentSpec",
    "ToolRegistry",
    "agent_registry",
    "register_k12_agents",
    "register_prompt_agents",
    "tool_registry",
]
