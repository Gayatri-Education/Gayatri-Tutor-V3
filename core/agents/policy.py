
from dataclasses import dataclass

@dataclass
class AgentPolicy:
    max_steps: int = 12
    time_budget_s: float = 60.0
    tool_budget: int = 20
    token_budget: int | None = None
