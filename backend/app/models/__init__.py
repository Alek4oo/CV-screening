"""ORM моделите на домейна.

Импортът тук регистрира всички таблици в Base.metadata — затова миграциите и
create_all-ът трябва да минат през `app.models`, а не през отделните модули.
"""

from app.models.audit_log import AuditAction, AuditLog
from app.models.candidate import Candidate
from app.models.decision import Decision, DecisionOutcome
from app.models.ranking import Ranking, RankingMode
from app.models.role import Role, RoleStatus
from app.models.ruleset import Ruleset, RulesetStatus

__all__ = [
    "AuditAction",
    "AuditLog",
    "Candidate",
    "Decision",
    "DecisionOutcome",
    "Ranking",
    "RankingMode",
    "Role",
    "RoleStatus",
    "Ruleset",
    "RulesetStatus",
]
