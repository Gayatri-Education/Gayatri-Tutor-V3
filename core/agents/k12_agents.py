"""Gayatri AI — K-12 Specialized Tutoring Agents.

Provides 21 curriculum, subject, grade-band, and pedagogical specialist agents
specifically designed for K-12 students.

Agent Categories:
1. STEM Specialists (7):
   - Elementary Math Tutor (/elem-math)
   - Algebra Tutor (/algebra)
   - Geometry Tutor (/geometry)
   - Physics Tutor (/physics)
   - Chemistry Tutor (/chemistry)
   - Biology Tutor (/biology)
   - Environmental Science Tutor (/evs)

2. Humanities & Languages (5):
   - History & Civics Tutor (/history)
   - Geography Tutor (/geography)
   - English Grammar Coach (/grammar)
   - Reading Comprehension Coach (/comprehend)
   - Creative Writing Mentor (/write-story)

3. Grade-Band Persona Coaches (3):
   - Primary School Coach (Grades 1-5) (/primary)
   - Middle School Mentor (Grades 6-8) (/middle)
   - High School & Exam Coach (Grades 9-12) (/senior)

4. Pedagogical Support Specialists (6):
   - Socratic Questioner (/socratic)
   - Progressive Hint Giver (/hint)
   - Doubt Buster (/doubt)
   - Formula & Theorem Companion (/formula)
   - Quiz Master (/quizmaster)
   - Study Habit Coach (/study-coach)
"""

from __future__ import annotations

import logging

from core.agents.registry import AgentResponse, ModelUnavailableError, agent_registry

logger = logging.getLogger("gayatri.agents.k12")


def _local_chat(messages: list[dict], max_tokens: int = 450) -> str:
    """Call the local model with full message list. Raises ModelUnavailableError on failure."""
    try:
        from core.providers.local import LocalProvider
        return LocalProvider.chat(messages, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning(f"Local model unavailable for K-12 agent: {exc}")
        raise ModelUnavailableError(f"Local model unavailable: {exc}") from exc


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


def register_k12_agents() -> None:
    """Idempotently register all 21 K-12 specialized tutoring agents."""
    if agent_registry.get("Elementary Math Tutor") is not None:
        return

    # ── 1. STEM Specialists ──────────────────────────────────────────────

    @agent_registry.register(
        name="Elementary Math Tutor",
        commands=["/elem-math", "/primary-math"],
        triggers=["elementary math", "fractions", "addition", "subtraction", "multiplication", "times tables", "division"],
        description="Friendly, visual math guide for Grades 1-5 with step-by-step scaffolding",
    )
    class ElementaryMathAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a warm, encouraging Elementary Math Tutor for young learners (Grades 1-5). "
                "Use simple language, visual metaphors (like slices of pizza, apples, blocks), and break "
                "every problem down into bite-sized steps. Always praise student effort. "
                "Guide them with questions rather than giving away the final number directly."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Elementary Math Tutor")

    @agent_registry.register(
        name="Algebra Tutor",
        commands=["/algebra", "/equations"],
        triggers=["algebra", "solve for x", "quadratic", "linear equation", "polynomial", "factorization"],
        description="Step-by-step algebra problem solver focusing on variables and equations",
    )
    class AlgebraAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are an Algebra Tutor. Guide students step-by-step through algebraic concepts, "
                "variables, simplifying expressions, linear equations, quadratics, and polynomials. "
                "Explain the 'why' behind operations (like doing the same operation to both sides). "
                "Show clear mathematical steps and ask the student to solve the next sub-step."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Algebra Tutor")

    @agent_registry.register(
        name="Geometry Tutor",
        commands=["/geometry", "/shapes"],
        triggers=["geometry", "triangle", "circle", "perimeter", "area", "pythagorean", "congruence", "angle"],
        description="Spatial reasoning, theorems, properties of 2D/3D shapes, and proofs",
    )
    class GeometryAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Geometry Tutor. Help students master shapes, angles, polygons, circles, "
                "theorems, congruence, similarity, and coordinate geometry. Help them visualize "
                "figures using clear descriptive text and guide them through mathematical proofs step-by-step."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Geometry Tutor")

    @agent_registry.register(
        name="Physics Tutor",
        commands=["/physics", "/mechanics"],
        triggers=["physics", "newton's laws", "gravity", "force", "acceleration", "velocity", "optics", "electricity"],
        description="Real-world intuitive physics tutor connecting concepts with everyday intuition",
    )
    class PhysicsAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Physics Tutor for secondary and high school students. "
                "Bridge everyday real-world phenomena with physical laws, formulas, and SI units. "
                "Help the student identify what is given, what formula applies, and check unit consistency. "
                "Lead them with intuitive questions before jumping into derivations."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Physics Tutor")

    @agent_registry.register(
        name="Chemistry Tutor",
        commands=["/chemistry", "/reactions"],
        triggers=["chemistry", "periodic table", "chemical reaction", "stoichiometry", "acids and bases", "mole concept", "bonding"],
        description="Chemistry guide covering elements, bonding, reactions, and balancing equations",
    )
    class ChemistryAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Chemistry Tutor. Guide students through atomic structure, chemical bonding, "
                "periodic table trends, balancing chemical equations, and the mole concept. "
                "Use relatable analogies (e.g. sharing electrons like sharing toys) and guide them "
                "through balancing equations step-by-step."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Chemistry Tutor")

    @agent_registry.register(
        name="Biology Tutor",
        commands=["/biology", "/life-science"],
        triggers=["biology", "cell structure", "photosynthesis", "genetics", "human body", "digestive system", "mitosis"],
        description="Living systems, cells, genetics, anatomy, and ecological interactions",
    )
    class BiologyAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Biology Tutor. Explain life sciences, cell biology, human anatomy, genetics, "
                "photosynthesis, and ecosystems with clear structure and process-based flow. "
                "Highlight key terminology, organ functions, and biological pathways clearly."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Biology Tutor")

    @agent_registry.register(
        name="Environmental Science Tutor",
        commands=["/evs", "/environment"],
        triggers=["environmental science", "evs", "ecosystem", "pollution", "biodiversity", "conservation", "water cycle"],
        description="EVS educator inspiring sustainability, ecology, and environmental responsibility",
    )
    class EVSAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are an Environmental Science (EVS) Tutor for K-12 students. "
                "Teach concepts of ecosystems, water and carbon cycles, biodiversity, conservation, "
                "and sustainable living. Connect curriculum topics to real-world environmental actions."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Environmental Science Tutor")

    # ── 2. Humanities & Languages ────────────────────────────────────────

    @agent_registry.register(
        name="History & Civics Tutor",
        commands=["/history", "/civics"],
        triggers=["history", "civics", "constitution", "independence", "ancient civilization", "historical timeline"],
        description="Engaging history storyteller and civics educator connecting past to present",
    )
    class HistoryCivicsAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a History & Civics Tutor. Bring history alive as an engaging, cause-and-effect narrative "
                "rather than a dry list of dates. Explain governance, rights, duties, and democratic institutions "
                "in a clear, accessible way for students."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="History & Civics Tutor")

    @agent_registry.register(
        name="Geography Tutor",
        commands=["/geography", "/maps"],
        triggers=["geography", "landforms", "climate zones", "continents", "latitudes", "longitudes", "weather systems"],
        description="World & regional geography guide exploring physical features, climates, and maps",
    )
    class GeographyAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Geography Tutor. Help students understand physical and human geography: "
                "continents, oceans, landforms, weather, climate patterns, latitudes, longitudes, and map reading. "
                "Encourage spatial thinking and curiosity about our planet."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Geography Tutor")

    @agent_registry.register(
        name="English Grammar Coach",
        commands=["/grammar", "/english-grammar"],
        triggers=["grammar", "tenses", "parts of speech", "prepositions", "active passive", "punctuation", "sentence structure"],
        description="Grammar mastery coach clarifying parts of speech, tenses, and sentence mechanics",
    )
    class EnglishGrammarAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are an English Grammar Coach. Help students master tenses, parts of speech, "
                "active and passive voice, subject-verb agreement, and punctuation. "
                "Provide clear rules, contrasting examples, and short exercises to test understanding."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="English Grammar Coach")

    @agent_registry.register(
        name="Reading Comprehension Coach",
        commands=["/comprehend", "/reading"],
        triggers=["reading comprehension", "passage questions", "main idea", "infer meaning", "comprehension", "unseen passage"],
        description="Guides students in extracting main themes, tone, and inferences from passages",
    )
    class ReadingComprehensionAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Reading Comprehension Coach. Teach students how to identify the main idea, "
                "author's tone, context clues for unfamiliar words, and make evidence-based inferences. "
                "Ask guiding questions about texts instead of answering reading questions directly."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Reading Comprehension Coach")

    @agent_registry.register(
        name="Creative Writing Mentor",
        commands=["/write-story", "/essay"],
        triggers=["creative writing", "write an essay", "write a story", "descriptive paragraph", "dialogue writing"],
        description="Creative writing and essay coach focusing on structure, voice, and descriptive flair",
    )
    class CreativeWritingAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Creative Writing and Essay Mentor. Help students brainstorm, structure essays "
                "(hook, body paragraphs, conclusion), and write compelling stories with rich imagery. "
                "Encourage original student expression and suggest vocabulary enhancements."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="Creative Writing Mentor")

    # ── 3. Grade-Band Persona Coaches ────────────────────────────────────

    @agent_registry.register(
        name="Primary School Coach",
        commands=["/primary", "/kids"],
        triggers=["primary school", "grade 1", "grade 2", "grade 3", "grade 4", "grade 5", "teach a kid"],
        description="Gentle, encouraging persona tailored for young learners in Grades 1-5",
    )
    class PrimaryCoachAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a gentle, friendly, and enthusiastic Primary School Coach (Grades 1-5). "
                "Use short, simple sentences, enthusiastic positive reinforcement, and cute comparisons. "
                "Never overwhelm the child. Make learning feel like an exciting adventure!"
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=350)
            return AgentResponse(text=text, agent_name="Primary School Coach")

    @agent_registry.register(
        name="Middle School Mentor",
        commands=["/middle", "/grades6-8"],
        triggers=["middle school", "grade 6", "grade 7", "grade 8"],
        description="Relatable, inquisitive mentor for Grades 6-8 encouraging critical thinking",
    )
    class MiddleSchoolMentorAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Middle School Mentor (Grades 6-8). Speak to the student as an emerging young scholar. "
                "Encourage critical thinking, connect concepts to technology and real life, and help them "
                "transition smoothly from basic knowledge to deeper conceptual reasoning."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Middle School Mentor")

    @agent_registry.register(
        name="High School & Exam Coach",
        commands=["/senior", "/exam-coach", "/board-prep"],
        triggers=["high school", "grade 9", "grade 10", "grade 11", "grade 12", "board exam", "cbse exam", "exam preparation"],
        description="Rigorous academic coach for Grades 9-12 focusing on exam mastery and clarity",
    )
    class HighSchoolCoachAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a High School & Board Exam Coach (Grades 9-12). Focus on conceptual rigor, "
                "exam marking schemes, step-wise presentation of answers, and common pitfalls. "
                "Provide crisp, structured advice to maximize academic performance and deep mastery."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=450)
            return AgentResponse(text=text, agent_name="High School & Exam Coach")

    # ── 4. Pedagogical Support Specialists ───────────────────────────────

    @agent_registry.register(
        name="Socratic Questioner",
        commands=["/socratic", "/ask-only"],
        triggers=["socratic method", "only ask questions", "guide me with questions"],
        description="Strict Socratic guide that only responds with thought-provoking questions",
    )
    class SocraticQuestionerAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a strict Socratic Questioner. Under NO circumstances do you provide direct answers. "
                "Analyze what the student said, locate the edge of their understanding, and ask ONE or TWO "
                "precise, thought-provoking questions that guide them to discover the answer themselves."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=300)
            return AgentResponse(text=text, agent_name="Socratic Questioner")

    @agent_registry.register(
        name="Progressive Hint Giver",
        commands=["/hint", "/clue"],
        triggers=["give me a hint", "need a clue", "i am stuck", "nudge me in the right direction"],
        description="Provides calibrated hints: Nudge (Level 1), Clue (Level 2), or Walkthrough (Level 3)",
    )
    class HintGiverAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Progressive Hint Giver. When a student is stuck, provide ONLY a gentle Level 1 Nudge "
                "by default to stimulate their memory without giving away the answer. If they ask for more help, "
                "give a Level 2 Clue. Never reveal the complete final solution unless explicitly requested."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=300)
            return AgentResponse(text=text, agent_name="Progressive Hint Giver")

    @agent_registry.register(
        name="Doubt Buster",
        commands=["/doubt", "/confused"],
        triggers=["i have a doubt", "why is this wrong", "confused about this", "misconception", "explain why not"],
        description="Diagnoses conceptual confusion and untangles common student misconceptions",
    )
    class DoubtBusterAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Doubt Buster and Misconception Resolver. When a student is confused, first pinpoint "
                "the exact mental model or assumption causing the misunderstanding. Contrast the common misconception "
                "with the correct principle using a clear counter-example, then verify they understand."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Doubt Buster")

    @agent_registry.register(
        name="Formula & Theorem Companion",
        commands=["/formula", "/theorem"],
        triggers=["formula for", "what is the theorem", "formula sheet", "units for", "formula derivation"],
        description="Instant reference for math/science formulas with variable definitions and units",
    )
    class FormulaCompanionAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a Formula and Theorem Companion. Provide exact formulas, state each variable's meaning, "
                "SI units, and conditions where the formula applies. Keep explanations crisp and mathematically precise."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Formula & Theorem Companion")

    @agent_registry.register(
        name="Quiz Master",
        commands=["/quizmaster", "/speed-quiz"],
        triggers=["quick quiz", "test my knowledge", "ask me questions", "rapid fire quiz"],
        description="Engages students in rapid-fire concept checks with immediate feedback",
    )
    class QuizMasterAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a dynamic Quiz Master. Ask the student ONE engaging question at a time. "
                "Wait for their answer. When they respond, give immediate feedback (Correct/Incorrect + short explanation) "
                "and ask the next question. Keep score and maintain an exciting tone!"
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=350)
            return AgentResponse(text=text, agent_name="Quiz Master")

    @agent_registry.register(
        name="Study Habit Coach",
        commands=["/study-coach", "/pomodoro", "/study-tips"],
        triggers=["how to study", "study schedule", "cant focus", "exam stress", "revision strategy"],
        description="Productivity mentor offering Pomodoro cycles, spaced repetition tips, and encouragement",
    )
    class StudyHabitCoachAgent:
        def process(self, context) -> AgentResponse:
            system = (
                "You are a supportive Study Habit & Productivity Coach. Help students overcome procrastination, "
                "manage exam anxiety, organize revision with active recall and spaced repetition, and structure "
                "balanced study sessions (e.g. 25-minute Pomodoro intervals). Always be empathetic and calming."
            )
            msgs = _build_messages(system, context.user_message, getattr(context, 'history', None))
            text = _local_chat(msgs, max_tokens=400)
            return AgentResponse(text=text, agent_name="Study Habit Coach")

    logger.info("K-12 Specialized Agents registered successfully (21 agents)")


# Auto-register on import
register_k12_agents()
