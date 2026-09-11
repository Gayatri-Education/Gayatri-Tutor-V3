"""Gayatri AI — Orchestrator: routes a user turn through agents → model → response.

LDG integration: when the Tutor agent is invoked, the orchestrator:
1. Loads the Learning Dependency Graph
2. Selects the next appropriate concept
3. Injects concept context into AgentContext.metadata
4. After the turn, updates mastery based on student response
"""

from __future__ import annotations

import logging
import threading
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

# LDG and TutorEngine lazy init with reentrant lock
_init_lock = threading.RLock()
_ldg: Any = None
_tutor_engine: Any = None


def _get_ldg():
    """Lazy-load the Learning Dependency Graph with default curriculum."""
    global _ldg
    if _ldg is None:
        with _init_lock:
            if _ldg is None:
                try:
                    from core.config import LDG_CURICULUM_DIR
                    from core.knowledge_graph import LearningDependencyGraph, load_curriculum
                    ldg = LearningDependencyGraph()
                    curriculum_path = LDG_CURICULUM_DIR / "python_basics.json"
                    if curriculum_path.exists():
                        load_curriculum(ldg, curriculum_path)
                        logger.info(f"LDG loaded: {curriculum_path}")
                    else:
                        logger.info("LDG initialized (no default curriculum)")
                    _ldg = ldg
                except Exception as exc:
                    logger.error(f"LDG init failed: {exc}")
                    _ldg = None
    return _ldg


def _get_tutor_engine():
    """Lazy-load the Tutor Engine with LDG."""
    global _tutor_engine
    if _tutor_engine is None:
        with _init_lock:
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
        settings = get_settings()
        if settings.get("router_preference") == "local_only":
            return ExecutionMode.LOCAL_ONLY
        mode_str = settings.get("privacy_mode", "local_only")
        return ExecutionMode(mode_str)
    except (ValueError, Exception):
        # Default to safest mode
        return ExecutionMode.LOCAL_ONLY


def _inject_tutor_context(context: AgentContext, session_id: str,
                          tutor: Any = None, ldg: Any = None) -> None:
    """Inject LDG concept context into AgentContext.metadata for Tutor agent.

    Side-effect: mutates context.metadata in place.
    """
    tutor = tutor or _get_tutor_engine()
    ldg = ldg or _get_ldg()
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
                if pc and (ldg.get_mastery(pid) or 0.0) < 0.85:
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


def _evaluate_tutor_response(session_id: str, user_message: str, agent_response: str,
                             tutor: Any = None, ldg: Any = None) -> None:
    """Evaluate student response and update LDG mastery.

    Called during the Tutor agent turn before generating response.
    Uses heuristic detection with staleness, duplicate, and question checks (Audit #36 & #130).
    """
    tutor = tutor or _get_tutor_engine()
    ldg = ldg or _get_ldg()
    if not tutor or not ldg:
        return

    try:
        ctx = tutor.get_or_create_context(session_id)
        if not ctx.current_concept_id:
            return

        # Staleness check (Audit #130): only evaluate if tutor was actively waiting
        if not tutor.is_waiting_for_answer(session_id):
            return

        lower_msg = user_message.lower().strip()

        # Check if user is asking a clarification/question rather than giving a wrong answer
        # e.g. "no, wait, what is a variable?" or "can you explain?"
        is_clarification = (
            "?" in lower_msg
            or any(lower_msg.startswith(w) for w in ("what", "why", "how", "who", "when", "where", "can you", "could you", "explain", "help me understand"))
            or "wait" in lower_msg
        )

        if is_clarification and lower_msg not in ("?", "help", "idk", "i don't know"):
            correct = None  # Student asking a question / seeking clarification, do not penalize
        elif len(lower_msg) < 3:
            correct = False
        elif lower_msg in ("i don't know", "idk", "?", "help", "i'm stuck", "no idea"):
            correct = False
        elif lower_msg.startswith(("yes", "yeah", "yep", "correct", "right", "i think", "it is")):
            correct = True
        elif lower_msg.startswith(("no", "nope", "wrong", "incorrect", "not")):
            correct = False
        else:
            correct = None  # uncertain, do not increase mastery

        mastery = tutor.record_student_response(
            session_id,
            correct=correct,
            student_answer=user_message,
        )
        logger.info(
            f"Evaluated response for {ctx.current_concept_name}: "
            f"{'correct' if correct else 'incorrect' if correct is False else 'uncertain'}, mastery={mastery:.3f}"
        )
    except Exception as exc:
        logger.error(f"Failed to evaluate tutor response: {exc}")


def _post_tutor_response(session_id: str, tutor: Any = None) -> None:
    """Mark the tutor as waiting for an answer after it responds."""
    tutor = tutor or _get_tutor_engine()
    if tutor:
        tutor.set_waiting_for_answer(session_id)


_TASK_TYPE_AGENTS: dict[str, str] = {
    "tutor": "Tutor",
    "practice": "Practice Generator",
    "quiz": "Practice Generator",
    "code": "Code Reviewer",
    "review": "Code Reviewer",
    "orchestrate": "Orchestrator Agent",
    "plan": "Orchestrator Agent",
}


@dataclass
class TurnOptions:
    """Options for a single turn."""
    task_type: str = "auto"
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    model_override: str | None = None
    forced_tier: str | None = None
    forced_agent: str | None = None


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
    status: str = "SUCCESS"  # "SUCCESS" | "MODEL_UNAVAILABLE" | "ERROR"


class Orchestrator:
    """Routes user messages through the agent pipeline and local model.

    LDG integration: Tutor agent gets concept context injected.
    Multi-turn conversation history maintained per session.
    Thread-safe turn processing and dependency-injected session management.
    """

    def __init__(
        self,
        registry=None,
        runtime=None,
        conversations: ConversationStore | None = None,
        tutor_engine: Any = None,
        ldg: Any = None,
    ):
        if registry is None:
            from core.agents.default_agents import register_default_agents
            register_default_agents()
        self.registry = registry or agent_registry
        self.runtime = runtime or AgentRuntime(registry=self.registry)
        self.conversations = conversations if conversations is not None else _conversations
        self._tutor_engine = tutor_engine
        self._ldg = ldg
        self._lock = threading.RLock()

    def get_tutor_engine(self) -> Any:
        """Get the bound TutorEngine or fall back to global singleton."""
        if self._tutor_engine is not None:
            return self._tutor_engine
        return _get_tutor_engine()

    def get_ldg(self) -> Any:
        """Get the bound LDG or fall back to global singleton."""
        if self._ldg is not None:
            return self._ldg
        return _get_ldg()

    def _get_conversation(self, session_id: str) -> Conversation:
        return self.conversations.get(session_id)

    def _resolve_agent(self, user_message: str, opts: TurnOptions):
        """Resolve agent dispatch taking forced_agent and task_type into account."""
        if opts.forced_agent and opts.forced_agent.lower() != "auto":
            spec = self.registry.get(opts.forced_agent)
            if spec is not None:
                logger.info(f"Forced agent dispatch: {spec.name}")
                return spec, 1.0, f"forced_agent:{spec.name}"
            logger.warning(f"Forced agent '{opts.forced_agent}' not found; checking task_type / auto-dispatch.")

        if opts.task_type and opts.task_type.lower() != "auto":
            task_key = opts.task_type.lower().strip()
            # If task_type indicates a speed preference, map to forced_tier
            if task_key in ("fast", "speed") and not opts.forced_tier:
                opts.forced_tier = "fast"
            elif task_key in ("reasoning", "slow") and not opts.forced_tier:
                opts.forced_tier = "slow"
            elif task_key in ("medium", "balanced") and not opts.forced_tier:
                opts.forced_tier = "medium"

            agent_name = _TASK_TYPE_AGENTS.get(task_key) or opts.task_type
            spec = self.registry.get(agent_name)
            if spec is not None:
                logger.info(f"Task type forced agent dispatch: {spec.name} for task '{opts.task_type}'")
                return spec, 1.0, f"task_type:{opts.task_type}"

        dispatch = self.registry.dispatch(user_message)
        if dispatch is not None:
            spec, confidence = dispatch
            return spec, confidence, f"agent_dispatch:{spec.name}:{confidence:.2f}"
        return None

    def _resolve_provider(self, opts: TurnOptions, exec_mode: ExecutionMode) -> tuple[Any, str, str]:
        """Resolve LLM provider and model based on model_override, forced_tier, and privacy mode.

        Returns: (provider_instance_or_class, model_id, routing_reason)
        """
        from core.providers.local import LocalProvider

        if opts.model_override:
            override = opts.model_override.strip()
            if override.lower() == "local":
                return LocalProvider, "local", "model_override:local"

            # Enforce privacy mode: cloud overrides strictly prohibited in LOCAL_ONLY mode
            if exec_mode == ExecutionMode.LOCAL_ONLY:
                raise PermissionError(
                    f"Data cannot leave the device: model_override '{override}' "
                    "is blocked because privacy mode is set to 'local_only'."
                )

            from core.providers.registry import get_registry
            registry = get_registry()
            target_provider = None
            target_model_id = override

            if "/" in override:
                pkey, mid = override.split("/", 1)
                target_provider = registry.get(pkey)
                target_model_id = mid
            else:
                target_provider = registry.get(override)
                if target_provider is not None:
                    models = target_provider.list_models()
                    target_model_id = models[0].id if models else override
                else:
                    for p in registry._providers.values():
                        for m in p.list_models():
                            if m.id == override:
                                target_provider = p
                                target_model_id = m.id
                                break
                        if target_provider:
                            break

            if target_provider is None:
                raise ValueError(f"Unknown or unconfigured provider/model override: '{override}'")

            if not registry._check_provider_available(target_provider):
                raise RuntimeError(
                    f"Provider '{target_provider.name}' for model '{target_model_id}' is not ready or available."
                )

            return target_provider, target_model_id, f"model_override:{target_provider.key}/{target_model_id}"

        if opts.forced_tier:
            if exec_mode == ExecutionMode.LOCAL_ONLY:
                logger.info(f"Forced tier '{opts.forced_tier}' mapped to local model due to LOCAL_ONLY mode.")
                return LocalProvider, "local", f"forced_tier_local_only:{opts.forced_tier}"

            from core.providers.base import SpeedTier
            from core.providers.registry import get_registry
            try:
                tier = SpeedTier(opts.forced_tier.lower())
            except ValueError:
                tier = SpeedTier.MEDIUM

            chain = get_registry().get_fallback_chain(tier)
            if chain:
                prov, model_info = chain[0]
                return prov, model_info.id, f"forced_tier:{tier.value}:{prov.key}/{model_info.id}"
            return LocalProvider, "local", f"forced_tier_fallback_local:{opts.forced_tier}"

        return LocalProvider, "local", "no_agent_match:local_fallback"

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
        dispatch = self._resolve_agent(user_message, opts)

        if dispatch is not None:
            spec, confidence, agent_routing_reason = dispatch
            logger.info(f"Agent dispatch: {spec.name} (confidence: {confidence:.2f})")

            context = AgentContext(
                session_id=session_id,
                user_message=user_message,
                model_tier=opts.forced_tier or "local",
                model_override=opts.model_override,
                history=conv.get_messages_for_model()[-10:],
            )

            # Inject LDG context for Tutor agent (transactional, Audit #128)
            tutor_txn = None
            if spec.name == "Tutor":
                tutor_eng = self.get_tutor_engine()
                if tutor_eng and hasattr(tutor_eng, "begin_transaction"):
                    tutor_txn = tutor_eng.begin_transaction(session_id)

                _evaluate_tutor_response(
                    session_id, user_message, "",
                    tutor=tutor_eng, ldg=self.get_ldg()
                )
                _inject_tutor_context(
                    context, session_id,
                    tutor=tutor_eng, ldg=self.get_ldg()
                )

            try:
                response = self.runtime.process(user_message, context, spec=spec)
            except Exception as proc_exc:
                if tutor_txn:
                    tutor_txn.rollback()
                raise proc_exc

            resp_status = getattr(response, "status", "SUCCESS")
            resp_text = response.text or ""

            if resp_status == "MODEL_UNAVAILABLE":
                logger.warning(f"Agent {spec.name} reported MODEL_UNAVAILABLE")
                if tutor_txn:
                    tutor_txn.rollback()
                conv.add("user", user_message, agent_name=spec.name)
                latency = (time.time() - start) * 1000
                return TurnResult(
                    text=resp_text or "The local AI model is not installed or unavailable. Please download the model file to enable this agent.",
                    model_used=f"agent:{spec.name}",
                    routing_reason="agent_error:model_unavailable",
                    latency_ms=latency,
                    agent_name=spec.name,
                    execution_mode=exec_mode.value,
                    status="MODEL_UNAVAILABLE",
                )

            if resp_status == "ERROR":
                logger.error(f"Agent {spec.name} reported ERROR")
                if tutor_txn:
                    tutor_txn.rollback()
                conv.add("user", user_message, agent_name=spec.name)
                latency = (time.time() - start) * 1000
                return TurnResult(
                    text=resp_text or f"Agent '{spec.name}' encountered an error processing your request.",
                    model_used=f"agent:{spec.name}",
                    routing_reason="agent_error",
                    latency_ms=latency,
                    agent_name=spec.name,
                    execution_mode=exec_mode.value,
                    status="ERROR",
                )

            if spec.name == "Tutor":
                _post_tutor_response(session_id, tutor=self.get_tutor_engine())
                if tutor_txn:
                    tutor_txn.commit()
            conv.add("user", user_message, agent_name=spec.name)
            conv.add("assistant", resp_text, agent_name=spec.name)
            latency = (time.time() - start) * 1000
            return TurnResult(
                text=resp_text,
                model_used=f"agent:{spec.name}",
                routing_reason=agent_routing_reason,
                latency_ms=latency,
                agent_name=spec.name,
                execution_mode=exec_mode.value,
                status="SUCCESS",
            )

        # 2. No agent matched — query resolved model
        try:
            provider, model_id, routing_reason = self._resolve_provider(opts, exec_mode)
            logger.info(f"Routing turn to {model_id} via {routing_reason}")

            from core.settings import get_settings
            sys_prompt = get_settings().get("system_prompt", "You are Gayatri AI, a helpful learning assistant.")
            messages = [
                {"role": "system", "content": sys_prompt},
            ]
            for msg in conv.get_recent(10):
                if msg.role in ("user", "assistant"):
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": user_message})

            from core.providers.local import LocalProvider
            if provider is LocalProvider:
                text = LocalProvider.chat(
                    messages,
                    max_tokens=opts.max_tokens,
                    temperature=opts.temperature,
                )
            else:
                from core.providers.base import ChatMessage, ChatOptions
                chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
                chat_opts = ChatOptions(
                    model=model_id,
                    max_tokens=opts.max_tokens,
                    temperature=opts.temperature,
                )
                resp = provider.chat(chat_msgs, options=chat_opts)
                text = resp.text

            conv.add("user", user_message)
            conv.add("assistant", text)

            latency = (time.time() - start) * 1000
            return TurnResult(
                text=text,
                model_used=model_id,
                routing_reason=routing_reason,
                latency_ms=latency,
                execution_mode=exec_mode.value,
                status="SUCCESS",
            )
        except Exception as exc:
            from core.errors import sanitize_error
            sanitized = sanitize_error(exc, category="orchestrator_submit")
            conv.add("user", user_message)
            latency = (time.time() - start) * 1000
            return TurnResult(
                text=f"I encountered an error: {sanitized.user_message} (Reference: {sanitized.diagnostic_id})",
                model_used="local",
                routing_reason=f"error:{type(exc).__name__}",
                latency_ms=latency,
                execution_mode=exec_mode.value,
                status="ERROR",
            )

    def stream(self, user_message: str, session_id: str = "default",
               options: TurnOptions | None = None):
        """Process a user message and stream tokens back. Yields (token, is_done)."""
        opts = options or TurnOptions()
        exec_mode = _get_execution_mode()
        
        # Redact PII upfront so all agents and conversation history are safe
        user_message = _redact_pii(user_message)
        
        conv = self._get_conversation(session_id)

        dispatch = self._resolve_agent(user_message, opts)

        if dispatch is not None:
            spec, confidence, agent_routing_reason = dispatch
            logger.info(f"Agent dispatch (stream): {spec.name} ({confidence:.2f})")

            context = AgentContext(
                session_id=session_id,
                user_message=user_message,
                model_tier=opts.forced_tier or "local",
                model_override=opts.model_override,
                history=conv.get_messages_for_model()[-10:],
            )

            tutor_txn = None
            if spec.name == "Tutor":
                tutor_eng = self.get_tutor_engine()
                if tutor_eng and hasattr(tutor_eng, "begin_transaction"):
                    tutor_txn = tutor_eng.begin_transaction(session_id)

                _evaluate_tutor_response(
                    session_id, user_message, "",
                    tutor=tutor_eng, ldg=self.get_ldg()
                )
                _inject_tutor_context(
                    context, session_id,
                    tutor=tutor_eng, ldg=self.get_ldg()
                )

            try:
                response = self.runtime.process(user_message, context, spec=spec)
            except Exception as proc_exc:
                if tutor_txn:
                    tutor_txn.rollback()
                raise proc_exc

            resp_status = getattr(response, "status", "SUCCESS")
            resp_text = response.text or ""

            if resp_status == "MODEL_UNAVAILABLE":
                logger.warning(f"Agent {spec.name} reported MODEL_UNAVAILABLE in stream")
                if tutor_txn:
                    tutor_txn.rollback()
                conv.add("user", user_message, agent_name=spec.name)
                yield resp_text or "The local AI model is not installed or unavailable. Please download the model file to enable this agent.", True
                return

            if resp_status == "ERROR":
                logger.error(f"Agent {spec.name} reported ERROR in stream")
                if tutor_txn:
                    tutor_txn.rollback()
                conv.add("user", user_message, agent_name=spec.name)
                yield resp_text or f"Agent '{spec.name}' encountered an error processing your request.", True
                return

            if spec.name == "Tutor":
                _post_tutor_response(session_id, tutor=self.get_tutor_engine())
                if tutor_txn:
                    tutor_txn.commit()
            conv.add("user", user_message, agent_name=spec.name)
            conv.add("assistant", resp_text, agent_name=spec.name)
            yield resp_text, True
            return

        # No agent — stream from resolved model
        buffer = []
        try:
            provider, model_id, routing_reason = self._resolve_provider(opts, exec_mode)
            logger.info(f"Routing stream turn to {model_id} via {routing_reason}")

            from core.settings import get_settings
            sys_prompt = get_settings().get("system_prompt", "You are Gayatri AI, a helpful learning assistant.")
            messages = [
                {"role": "system", "content": sys_prompt},
            ]
            for msg in conv.get_recent(10):
                if msg.role in ("user", "assistant"):
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": user_message})

            from core.providers.local import LocalProvider
            if provider is LocalProvider:
                token_stream = LocalProvider.chat_stream(
                    messages,
                    max_tokens=opts.max_tokens,
                    temperature=opts.temperature,
                )
            else:
                from core.providers.base import ChatMessage, ChatOptions
                chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
                chat_opts = ChatOptions(
                    model=model_id,
                    max_tokens=opts.max_tokens,
                    temperature=opts.temperature,
                )
                token_stream = provider.stream(chat_msgs, options=chat_opts)

            for token in token_stream:
                buffer.append(token)
                yield token, False
        except Exception as exc:
            from core.errors import sanitize_error
            sanitized = sanitize_error(exc, category="orchestrator_stream")
            conv.add("user", user_message)
            raise RuntimeError(f"Streaming failed: {sanitized.user_message}") from exc

        full_text = "".join(buffer)
        conv.add("user", user_message)
        conv.add("assistant", full_text)
        yield "", True

    def clear_session(self, session_id: str = "default") -> None:
        with self._lock:
            conv = self._get_conversation(session_id)
            conv.clear()
            tutor = self.get_tutor_engine()
            if tutor and hasattr(tutor, "clear_session"):
                tutor.clear_session(session_id)
            try:
                from core.session import get_session_store
                get_session_store().clear_session_messages(session_id)
            except Exception as exc:
                logger.debug(f"Could not clear persisted session {session_id}: {exc}")

    def get_conversation(self, session_id: str = "default") -> Conversation:
        return self._get_conversation(session_id)

    def new_session(self, session_id: str = "default") -> Conversation:
        return self.conversations.new_session(session_id)

    def load_session(self, session_id: str, messages: list[dict],
                     tutor_context: Any = None) -> Conversation:
        """Load a previous session into the active conversation."""
        with self._lock:
            conv = self.new_session(session_id)
            for msg in messages:
                conv.add(msg["role"], msg["content"], agent_name=msg.get("agent_name", ""))

            tutor = self.get_tutor_engine()
            if tutor:
                if tutor_context is not None:
                    if hasattr(tutor, "set_context"):
                        tutor.set_context(session_id, tutor_context)
                    else:
                        tutor.session_contexts[session_id] = tutor_context
                else:
                    tutor.get_or_create_context(session_id)
            return conv
