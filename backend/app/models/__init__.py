"""ORM моделите на домейна.

Импортът тук регистрира всички таблици в Base.metadata — затова alembic/env.py
внася `app.models`, а не отделните модули. Пропуснат модул значи таблица, която
autogenerate не вижда и после предлага да изтрие.
"""

from app.models.audit_log import AuditAction, AuditLog
from app.models.bias_audit import BiasAudit
from app.models.candidate import Candidate
from app.models.decision import Decision, DecisionOutcome
from app.models.ranking import Ranking, RankingMode
from app.models.role import Role, RoleStatus
from app.models.ruleset import Ruleset, RulesetStatus

__all__ = [
    "AuditAction",
    "AuditLog",
    "BiasAudit",
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
