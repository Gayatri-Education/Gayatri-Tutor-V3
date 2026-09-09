"""Default agents registered with the global agent_registry on import.

Tutor agents are LDG-aware: they query the Learning Dependency Graph to
select concepts, track mastery, and adapt teaching based on student progress.

Teaching approach: Socratic method via the model's own capabilities.
This module provides concept context — the model handles the teaching strategy.
"""

from __future__ import annotations

import logging

from core.agents.registry import AgentResponse, agent_registry

logger = logging.getLogger("gayatri.agents.defaults")


def _local_chat(messages: list[dict], max_tokens: int = 300) -> str:
    """Call the local model with full message list. Falls back gracefully."""
    try:
        from core.providers.local import LocalProvider
        return LocalProvider.chat(messages, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning(f"Local model unavailable: {exc}")
        return (
            "I'm running without the local model right now. "
            "Once the model file is downloaded and placed in the models directory, "
            "I'll be able to help properly."
        )


def _build_messages(system: str, user_message: str,
                    history: list[dict] | None = None) -> list[dict]:
    """Build a message list with system prompt, optional history, and current user message."""
    messages = [{"role": "system", "content": system}]
    if history:
        for msg in history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _get_tutor_context(context) -> str:
    """Extract LDG-based tutor context from AgentContext.metadata."""
    tutor_meta = getattr(context, 'metadata', {}).get('tutor', {})
    if not tutor_meta:
        return ""

    parts = []
    if tutor_meta.get('concept_name'):
        parts.append(f"Current concept: {tutor_meta['concept_name']}")
    if tutor_meta.get('concept_description'):
        parts.append(f"About: {tutor_meta['concept_description']}")
    if tutor_meta.get('mastery_pct'):
        parts.append(f"Student mastery: {tutor_meta['mastery_pct']}")
    if tutor_meta.get('waiting_for_answer'):
        parts.append("You asked a question — wait for the student's answer before continuing.")
    if tutor_meta.get('prerequisites_not_met'):
        prereq_names = tutor_meta.get('prereq_names', [])
        parts.append(
            f"IMPORTANT: The student needs to master prerequisites first: "
            f"{', '.join(prereq_names)}. Start with the FIRST prerequisite."
        )
    if tutor_meta.get('recent_attempt'):
        correct = tutor_meta['recent_attempt'].get('correct')
        if correct is False:
            parts.append(
                "The student's last answer was incorrect. Gently correct them, "
                "explain the right approach, then ask another question to check."
            )
        elif correct is True:
            parts.append(
                "The student answered correctly. Praise them briefly, "
                "then advance to the next topic or ask a deeper question."
            )

    return "\n".join(parts)


def _build_tutor_system_prompt(context) -> str:
    """Build a system prompt for the Tutor agent with LDG context."""
    base = (
        "You are a patient Socratic tutor. Guide the student to answers through questions. "
        "Never give direct answers. Adapt explanations to their level. Use simple examples. "
        "Reference earlier parts of the conversation if relevant."
    )
    tutor_context = _get_tutor_context(context)
    if tutor_context:
        base += f"\n\nTeaching context:\n{tutor_context}"
    return base


def _build_practice_system_prompt(context) -> str:
    """Build a system prompt for the Practice Generator with LDG context."""
    base = (
        "Generate one practice problem based on the user's current learning concept. "
        "State the question clearly. Wait for the student's answer before "
        "giving the solution. Make it appropriate to their mastery level."
    )
    tutor_context = _get_tutor_context(context)
    if tutor_context:
        base += f"\n\nTeaching context:\n{tutor_context}"
    return base


def register_default_agents() -> None:
    """Idempotently register the four default agents plus all prompt-engineered agents."""
    # Register prompt-engineered agents first (idempotent)
    try:
        from core.agents.prompt_agents import register_prompt_agents as _reg_prompts
        _reg_prompts()
    except Exception:
        pass

    # Now register the four default agents (also idempotent)
    if agent_registry.get("Tutor") is not None:
        return

    @agent_registry.register(
        name="Tutor",
        commands=["/tutor", "/learn", "/teach"],
        triggers=[
            "help me understand",
            "explain to me",
            "teach me",
            "help me learn",
            "explain how",
        ],
        description="Socratic tutor — guides you to answers through questions",
    )
    class TutorAgent:
        def process(self, context) -> AgentResponse:
            system = _build_tutor_system_prompt(context)
            msgs = _build_messages(
                system,
                context.user_message,
                getattr(context, 'history', None),
            )
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Tutor")

    @agent_registry.register(
        name="Practice Generator",
        commands=["/practice", "/quiz", "/exercise"],
        triggers=[
            "give me practice",
            "quiz me",
            "exercises",
            "practice problems",
            "homework",
        ],
        description="Generates practice problems and exercises",
    )
    class PracticeAgent:
        def process(self, context) -> AgentResponse:
            system = _build_practice_system_prompt(context)
            msgs = _build_messages(
                system,
                context.user_message,
                getattr(context, 'history', None),
            )
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Practice Generator")

    @agent_registry.register(
        name="Code Reviewer",
        commands=["/review", "/check"],
        triggers=[
            "review my code",
            "check my code",
            "find bugs",
            "code review",
            "improve my code",
        ],
        description="Reviews code for bugs, style, and best practices",
    )
    class ReviewAgent:
        def process(self, context) -> AgentResponse:
            msgs = _build_messages(
                "You are a code reviewer. Review the code for bugs, security "
                "issues, style, and best practices. Be constructive and specific. "
                "If no code is provided, ask for it.",
                context.user_message,
                getattr(context, 'history', None),
            )
            text = _local_chat(msgs, max_tokens=500)
            return AgentResponse(text=text, agent_name="Code Reviewer")

    @agent_registry.register(
        name="Dispatcher",
        commands=["/agent", "/agents", "/help"],
        triggers=[
            "list agents",
            "what agents",
            "available agents",
            "help commands",
        ],
        description="Lists and manages available agents",
    )
    class DispatcherAgent:
        def process(self, context) -> AgentResponse:
            agents = agent_registry.list_agents()
            lines = ["Available agents:"]
            for a in agents:
                cmds = ", ".join(a["commands"]) if a["commands"] else "auto-detect"
                lines.append(f"  • {a['name']} — {a['description']} [{cmds}]")
            lines.append("\nType /agent <name> to invoke, or just talk naturally.")
            return AgentResponse(text="\n".join(lines), agent_name="Dispatcher")

    logger.info("Default agents registered")


register_default_agents()
