"""Agent discovery — all agents are auto-registered via @register_agent decorator.

The explicit imports below ensure each agent module is loaded (so the decorator runs).
New agents only need to:
  1. Add ``@register_agent`` on the class (in their own .py file)
  2. Add one import line here

The global registry is accessible via:
  from app.agents.base import get_registered_agents, get_agent_class
"""

from app.agents.conversation_agent import ConversationAgent      # noqa: F401
from app.agents.diagnosis_agent import DiagnosisAgent            # noqa: F401
from app.agents.grading_agent import GradingAgent                # noqa: F401
from app.agents.knowledge_agent import KnowledgeAgent            # noqa: F401
from app.agents.planner_agent import PlannerAgent                # noqa: F401
from app.agents.profile_agent import ProfileAgent                # noqa: F401
from app.agents.question_agent import QuestionAgent              # noqa: F401
from app.agents.resource_agent import ResourceAgent              # noqa: F401
from app.agents.review_agent import ReviewAgent                  # noqa: F401

from app.agents.base import get_agent_class, get_registered_agents  # noqa: F401, E402


__all__ = [
    "ConversationAgent",
    "DiagnosisAgent",
    "GradingAgent",
    "KnowledgeAgent",
    "PlannerAgent",
    "ProfileAgent",
    "QuestionAgent",
    "ResourceAgent",
    "ReviewAgent",
    "get_agent_class",
    "get_registered_agents",
]
