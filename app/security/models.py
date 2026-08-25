"""Sprint 23: the security model — deliberately small. No IAM framework,
no permission graph — just enough to make "which tenant can see this
chunk" a server-owned, structural question instead of a convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    USER = "USER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


# Role hierarchy for "at least this role" checks (require_role(OPERATOR)
# also accepts ADMIN) — a plain ordered list, not a graph, since roles
# here are linear (USER < OPERATOR < ADMIN), not a lattice.
_ROLE_ORDER = [Role.USER, Role.OPERATOR, Role.ADMIN]


def role_satisfies(actual: Role, required: Role) -> bool:
    return _ROLE_ORDER.index(actual) >= _ROLE_ORDER.index(required)


@dataclass(frozen=True)
class UserContext:
    """The server's OWN belief about who is making this request — built
    exclusively from a validated bearer token (app/security/auth.py),
    never from anything in the request body/query string. See
    app/api/deps.py::get_current_user, the only place one of these is
    constructed for a real request.
    """

    user_id: str
    tenant_id: str
    roles: frozenset[Role]

    def has_role(self, required: Role) -> bool:
        return any(role_satisfies(r, required) for r in self.roles)


@dataclass(frozen=True)
class RetrievalContext:
    """What app/retrieval/search.py actually authorizes against — a
    DELIBERATELY separate type from UserContext (Sprint 23 section 9):
    a UserContext always has a concrete tenant_id, but a RetrievalContext
    can be the explicit, privileged "no tenant restriction" case used by
    internal system code (migration/evaluation/benchmark), which must
    never be reachable by accident. tenant_id=None on its own does NOT
    mean "all tenants" — only is_system=True does; see
    app/retrieval/filters.py::build_acl_filter, which raises rather than
    silently building an unrestricted filter if tenant_id is None and
    is_system is False.
    """

    tenant_id: str | None
    is_system: bool = False

    @classmethod
    def for_user(cls, user: UserContext) -> RetrievalContext:
        return cls(tenant_id=user.tenant_id, is_system=False)

    @classmethod
    def system(cls) -> RetrievalContext:
        """Explicit privileged context for internal, non-request-driven
        code (migration re-indexing, evaluation/benchmark scripts) that
        legitimately needs to read across every tenant. Never construct
        this from request data — there is no code path that does.
        """
        return cls(tenant_id=None, is_system=True)
