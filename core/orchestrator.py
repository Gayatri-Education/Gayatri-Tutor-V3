"""Gayatri AI — Orchestrator: routes a user turn through agents → model → response.

LDG integration: when the Tutor agent is invoked, the orchestrator:
1. Loads the Learning Dependency Graph
2. Selects the next appropriate concept
3. Injects concept context into AgentContext.metadata
4. After the turn, updates mastery based on student response
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from core.agents.registry import agent_registry
from core.agents.runtime import AgentContext, AgentRuntime
from core.config import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE, ExecutionMode
from core.conversation import Conversation, ConversationStore
from core.privacy import get_redactor

logger = logging.getLogger("gayatri.orchestrator")

# Global conversation store — one conversation per session
_conversations = ConversationStore()

# LDG lazy init
_ldg: Any = None
_tutor_engine: Any = None


def _get_ldg():
    """Lazy-load the Learning Dependency Graph with default curriculum."""
    global _ldg
    if _ldg is None:
        try:
            from core.config import LDG_CURICULUM_DIR
            from core.knowledge_graph import LearningDependencyGraph, load_curriculum
            _ldg = LearningDependencyGraph()
            curriculum_path = LDG_CURICULUM_DIR / "python_basics.json"
            if curriculum_path.exists():
                load_curriculum(_ldg, curriculum_path)
                logger.info(f"LDG loaded: {curriculum_path}")
            else:
                logger.info("LDG initialized (no default curriculum)")
        except Exception as exc:
            logger.error(f"LDG init failed: {exc}")
            _ldg = None
    return _ldg


def _get_tutor_engine():
    """Lazy-load the Tutor Engine with LDG."""
    global _tutor_engine
    if _tutor_engine is None:
        try:
            from core.tutor_engine import TutorEngine
            ldg = _get_ldg()
            if ldg:
                _tutor_engine = TutorEngine(ldg)
                logger.info("TutorEngine initialized")
            else:
                logger.warning("TutorEngine: LDG not available")
        except Exception as exc:
            logger.error(f"TutorEngine init failed: {exc}")
            _tutor_engine = None
    return _tutor_engine


def _redact_pii(text: str) -> str:
    """Redact PII before sending to model."""
    redactor = get_redactor()
    result = redactor.redact(text)
    if result.has_pii:
        logger.info(f"PII redacted: {redactor.get_redaction_summary(result)}")
    return result.clean_text


def _get_execution_mode() -> ExecutionMode:
    """Read the current privacy/execution mode from settings."""
    try:
        from core.settings import get_settings
        mode_str = get_settings().get("privacy_mode", "local_only")
        return ExecutionMode(mode_str)
    except (ValueError, Exception):
        # Default to safest mode
        return ExecutionMode.LOCAL_ONLY


def _inject_tutor_context(context: AgentContext, session_id: str) -> None:
    """Inject LDG concept context into AgentContext.metadata for Tutor agent.

    Side-effect: mutates context.metadata in place.
    """
    tutor = _get_tutor_engine()
    ldg = _get_ldg()
    if not tutor or not ldg:
        return

    try:
        engine = tutor
        ctx = engine.get_or_create_context(session_id)
        concept = engine.get_next_concept_for_session(session_id)

        if concept:
            # Check if prerequisites are met
            prereqs = ldg.get_prerequisites(concept.id)
            prereq_names = []
            prerequisites_not_met = False
            for pid in prereqs:
                pc = ldg.get_concept(pid)
                if pc and ldg.get_mastery(pid) < 0.85:
                    prerequisites_not_met = True
                    prereq_names.append(pc.name)

            tutor_meta = {
                "concept_id": concept.id,
                "concept_name": concept.name,
                "concept_description": concept.description,
                "mastery_pct": f"{int(concept.mastery * 100)}%",
                "waiting_for_answer": ctx.waiting_for_answer,
                "prerequisites_not_met": prerequisites_not_met,
                "prereq_names": prereq_names,
            }

            # If waiting for answer, mark that
            if ctx.waiting_for_answer:
                tutor_meta["waiting_for_answer"] = True

            if getattr(ctx, 'last_attempt_correct', None) is not None:
                tutor_meta["recent_attempt"] = {"correct": ctx.last_attempt_correct}
                ctx.last_attempt_correct = None

            if not hasattr(context, 'metadata') or context.metadata is None:
                context.metadata = {}
            context.metadata["tutor"] = tutor_meta
            logger.debug(f"Injected tutor context: {concept.name} (mastery={concept.mastery:.2f})")
    except Exception as exc:
        logger.error(f"Failed to inject tutor context: {exc}")


def _evaluate_tutor_response(session_id: str, user_message: str, agent_response: str) -> None:
    """Evaluate student response and update LDG mastery.

    Called after the Tutor agent responds.
    Uses simple heuristics to detect correctness (no LLM-as-judge for privacy).
    """
    tutor = _get_tutor_engine()
    ldg = _get_ldg()
    if not tutor or not ldg:
        return

    try:
        ctx = tutor.get_or_create_context(session_id)
        if not ctx.current_concept_id:
            return

        # If tutor was waiting for an answer, evaluate it
        if ctx.waiting_for_answer:
            # Simple heuristics for correctness detection
            # (Avoids sending student answer back to model for privacy)
            lower_msg = user_message.lower().strip()

            # Very short / confused responses likely wrong
            if len(lower_msg) < 3:
                correct = False
            # Explicit "I don't know" / "help" / "?"
            elif lower_msg in ("i don't know", "idk", "?", "help", "i'm stuck", "no idea"):
                correct = False
            # Affirmative responses
            elif lower_msg.startswith(("yes", "yeah", "yep", "correct", "right", "i think", "it is")):
                correct = True
            # Negative responses
            elif lower_msg.startswith(("no", "nope", "wrong", "incorrect", "not")):
                correct = False
            else:
                correct = None  # uncertain, do not increase mastery

            mastery = tutor.record_student_response(session_id, correct=correct)
            logger.info(
                f"Evaluated response for {ctx.current_concept_name}: "
                f"{'correct' if correct else 'incorrect'}, mastery={mastery:.3f}"
            )
    except Exception as exc:
        logger.error(f"Failed to evaluate tutor response: {exc}")

def _post_tutor_response(session_id: str) -> None:
    """Mark the tutor as waiting for an answer after it responds."""
    tutor = _get_tutor_engine()
    if tutor:
        tutor.set_waiting_for_answer(session_id)


@dataclass
class TurnOptions:
    """Options for a single turn."""
    task_type: str = "auto"
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    model_override: str | None = None
    forced_tier: str | None = None


@dataclass
class TurnResult:
    """Result of processing one turn."""
    text: str
    model_used: str = "local"
    routing_reason: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    agent_name: str = ""
    execution_mode: str = "local_only"  # "local_only" | "cloud_allowed"


class Orchestrator:
    """Routes user messages through the agent pipeline and local model.

    LDG integration: Tutor agent gets concept context injected.
    Multi-turn conversation history maintained per session.
    """

    def __init__(self, registry=None, runtime=None):
        self.registry = registry or agent_registry
        self.runtime = runtime or AgentRuntime(registry=self.registry)

    def _get_conversation(self, session_id: str) -> Conversation:
        return _conversations.get(session_id)

    def submit(self, user_message: str, session_id: str = "default",
               options: TurnOptions | None = None) -> TurnResult:
        """Process a user message and return the full response."""
        opts = options or TurnOptions()
        start = time.time()
        exec_mode = _get_execution_mode()
        
        # Redact PII upfront so all agents and conversation history are safe
        user_message = _redact_pii(user_message)
        
        conv = self._get_conversation(session_id)

        # 1. Try agent dispatch
        dispatch = self.registry.dispatch(user_message)

        if dispatch is not None:
            spec, confidence = dispatch
            logger.info(f"Agent dispatch: {spec.name} (confidence: {confidence:.2f})")

            context = AgentContext(
                session_id=session_id,
                user_message=user_message,
                model_tier="local",
                history=conv.get_messages_for_model()[-10:],
            )

            # Inject LDG context for Tutor agent
            if spec.name == "Tutor":
                _evaluate_tutor_response(session_id, user_message, "")
                _inject_tutor_context(context, session_id)

            response = self.runtime.process(user_message, context, spec=spec)

            if response.text:
                if spec.name == "Tutor":
                    _post_tutor_response(session_id)
                conv.add("user", user_message, agent_name=spec.name)
                conv.add("assistant", response.text, agent_name=spec.name)
                latency = (time.time() - start) * 1000
                return TurnResult(
                    text=response.text,
                    model_used=f"agent:{spec.name}",
                    routing_reason=f"agent_dispatch:{spec.name}:{confidence:.2f}",
                    latency_ms=latency,
                    agent_name=spec.name,
                    execution_mode=exec_mode.value,
                )

        # 2. No agent matched — query the local model directly
        logger.info("No agent matched, using local model")
        try:
            from core.providers.local import LocalProvider

            messages = [
                {"role": "system", "content": "You are Gayatri AI, a helpful learning assistant."},
            ]
            for msg in conv.get_recent(10):
                if msg.role in ("user", "assistant"):
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": user_message})

            text = LocalProvider.chat(
                messages,
                max_tokens=opts.max_tokens,
                temperature=opts.temperature,
            )
        except Exception as exc:
            logger.error(f"Local model generation failed: {exc}")
            text = f"I encountered an error: {exc}. Please try again."

        conv.add("user", user_message)
        conv.add("assistant", text)

        latency = (time.time() - start) * 1000
        return TurnResult(
            text=text,
            model_used="local",
            routing_reason="no_agent_match:local_fallback",
            latency_ms=latency,
            execution_mode=exec_mode.value,
        )

    def stream(self, user_message: str, session_id: str = "default",
               options: TurnOptions | None = None):
        """Process a user message and stream tokens back. Yields (token, is_done)."""
        opts = options or TurnOptions()
        start = time.time()
        
        # Redact PII upfront so all agents and conversation history are safe
        user_message = _redact_pii(user_message)
        
        conv = self._get_conversation(session_id)

        dispatch = self.registry.dispatch(user_message)

        if dispatch is not None:
            spec, confidence = dispatch
            logger.info(f"Agent dispatch (stream): {spec.name} ({confidence:.2f})")

            context = AgentContext(
                session_id=session_id,
                user_message=user_message,
                model_tier="local",
                history=conv.get_messages_for_model()[-10:],
            )

            if spec.name == "Tutor":
                _evaluate_tutor_response(session_id, user_message, "")
                _inject_tutor_context(context, session_id)

            response = self.runtime.process(user_message, context, spec=spec)

            if response.text:
                if spec.name == "Tutor":
                    _post_tutor_response(session_id)
                conv.add("user", user_message, agent_name=spec.name)
                conv.add("assistant", response.text, agent_name=spec.name)
                yield response.text, True
                return

        # No agent — stream from local model
        buffer = []
        try:
            from core.providers.local import LocalProvider

            messages = [
                {"role": "system", "content": "You are Gayatri AI, a helpful learning assistant."},
            ]
            for msg in conv.get_recent(10):
                if msg.role in ("user", "assistant"):
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": user_message})

            for token in LocalProvider.chat_stream(
                messages,
                max_tokens=opts.max_tokens,
                temperature=opts.temperature,
            ):
                buffer.append(token)
                yield token, False
        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            error_text = f"[Error: {exc}]"
            buffer.append(error_text)
            yield error_text, True

        full_text = "".join(buffer)
        conv.add("user", user_message)
        conv.add("assistant", full_text)
        yield "", True

    def clear_session(self, session_id: str = "default") -> None:
        conv = self._get_conversation(session_id)
        conv.clear()

    def get_conversation(self, session_id: str = "default") -> Conversation:
        return self._get_conversation(session_id)

    def new_session(self, session_id: str = "default") -> Conversation:
        return _conversations.new_session(session_id)

    def load_session(self, session_id: str, messages: list[dict]) -> Conversation:
        """Load a previous session into the active conversation."""
        conv = self.new_session(session_id)
        for msg in messages:
            conv.add(msg["role"], msg["content"], agent_name=msg.get("agent_name", ""))
        return conv
