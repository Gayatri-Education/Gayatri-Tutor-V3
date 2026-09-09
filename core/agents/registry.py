"""Gayatri AI — Agent Registry.

Each agent is a self-contained class that registers itself with:
  - name: human-readable name
  - commands: list of /commands that trigger this agent
  - triggers: natural language patterns that trigger this agent
  - system_prompt: the system prompt for this agent
  - tools: list of tool names this agent can use
  - tier: preferred LLM tier (local/fast/quality)

Usage:
    from core.agents.registry import agent_registry

    @agent_registry.register(
        name="Code Reviewer",
        commands=["/review"],
        triggers=["review my code", "check for bugs"],
        system_prompt="You are a code reviewer...",
        tools=["run_code"],
    )
    class CodeReviewer:
        def process(self, request, context):
            return AgentResponse(...)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gayatri.agents")


@dataclass
class AgentSpec:
    """Metadata for a registered agent."""
    name: str
    commands: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    tier: str = "local"
    description: str = ""

    # Filled in by registry
    _class: type | None = field(default=None, repr=False, compare=False)

    def can_handle(self, text: str) -> tuple[bool, float]:
        """Check if this agent should handle the given text.

        Returns (should_handle, confidence).
        """
        text_lower = text.lower().strip()

        # Check explicit commands — match complete command token (word-boundary)
        # /transcribe must not match /trans (which is a prefix)
        for cmd in self.commands:
            cmd_lower = cmd.lower().lstrip("/")
            cmd_prefix = f"/{cmd_lower}"
            if text_lower.startswith(cmd_prefix):
                remainder = text_lower[len(cmd_prefix):]
                if remainder == "" or remainder[0] in (" ", "\t", "\n"):
                    return True, 1.0

        # Check trigger phrases (fuzzy match)
        best_score = 0.0
        for trigger in self.triggers:
            trigger_words = set(trigger.lower().split())
            text_words = set(text_lower.split())
            overlap = len(trigger_words & text_words)
            if overlap > 0:
                score = overlap / len(trigger_words)
                best_score = max(best_score, score)

        threshold = 0.6  # at least 60% of trigger words must match (reduces false positives)
        return best_score >= threshold, best_score


@dataclass
class AgentResponse:
    """Response from an agent."""
    text: str
    agent_name: str
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AgentRegistry:
    """Registry of all available agents.

    Agents register themselves via the @register decorator.
    The dispatcher queries this registry to find the best agent for a request.
    """

    def __init__(self):
        self._agents: dict[str, AgentSpec] = {}
        self._classes: dict[str, type] = {}

    def register(
        self,
        *,
        name: str,
        commands: list[str] | None = None,
        triggers: list[str] | None = None,
        system_prompt: str = "",
        tools: list[str] | None = None,
        tier: str = "local",
        description: str = "",
    ) -> Callable:
        """Decorator to register an agent class.

        Usage:
            @agent_registry.register(name="MyAgent", commands=["/my"])
            class MyAgent:
                def process(self, request, context) -> AgentResponse:
                    ...
        """
        def decorator(cls: type) -> type:
            spec = AgentSpec(
                name=name,
                commands=commands or [],
                triggers=triggers or [],
                system_prompt=system_prompt,
                tools=tools or [],
                tier=tier,
                description=description,
            )
            spec._class = cls
            self._agents[name] = spec
            self._classes[name] = cls
            logger.info(f"Registered agent: {name} ({len(spec.commands)} commands, {len(spec.triggers)} triggers)")
            return cls
        return decorator

    def get(self, name: str) -> AgentSpec | None:
        """Get an agent spec by name."""
        return self._agents.get(name)

    def get_class(self, name: str) -> type | None:
        """Get an agent class by name."""
        return self._classes.get(name)

    def list_agents(self) -> list[dict]:
        """List all registered agents (for UI display)."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "commands": spec.commands,
                "tier": spec.tier,
            }
            for spec in self._agents.values()
        ]

    def list_commands(self) -> list[str]:
        """List all registered /commands."""
        cmds = []
        for spec in self._agents.values():
            cmds.extend(spec.commands)
        return sorted(cmds)

    def dispatch(self, text: str) -> tuple[AgentSpec, float] | None:
        """Find the best agent for the given text.

        Returns (AgentSpec, confidence) or None if no agent matches.
        """
        best_agent = None
        best_score = 0.0

        for spec in self._agents.values():
            matches, score = spec.can_handle(text)
            if matches and score > best_score:
                best_score = score
                best_agent = spec

        if best_agent and best_score >= 0.6:
            logger.info(f"Dispatched to '{best_agent.name}' (confidence: {best_score:.2f})")
            return best_agent, best_score

        logger.info(f"No agent matched for: {text[:80]}")
        return None

    def instantiate(self, name: str, **kwargs) -> Any:
        """Create an instance of an agent by name."""
        cls = self._classes.get(name)
        if cls is None:
            raise ValueError(f"Agent '{name}' not registered")
        return cls(**kwargs)


# Global singleton
agent_registry = AgentRegistry()
