import pytest

from app.security.models import RetrievalContext, Role, UserContext, role_satisfies


def test_role_satisfies_is_reflexive():
    assert role_satisfies(Role.USER, Role.USER)
    assert role_satisfies(Role.OPERATOR, Role.OPERATOR)
    assert role_satisfies(Role.ADMIN, Role.ADMIN)


def test_role_satisfies_allows_higher_role_for_lower_requirement():
    assert role_satisfies(Role.ADMIN, Role.USER)
    assert role_satisfies(Role.OPERATOR, Role.USER)
    assert role_satisfies(Role.ADMIN, Role.OPERATOR)


def test_role_satisfies_rejects_lower_role_for_higher_requirement():
    assert not role_satisfies(Role.USER, Role.OPERATOR)
    assert not role_satisfies(Role.USER, Role.ADMIN)
    assert not role_satisfies(Role.OPERATOR, Role.ADMIN)


def test_user_context_has_role_checks_across_the_full_role_set():
    user = UserContext(user_id="u1", tenant_id="t1", roles=frozenset({Role.OPERATOR}))

    assert user.has_role(Role.USER)
    assert user.has_role(Role.OPERATOR)
    assert not user.has_role(Role.ADMIN)


def test_retrieval_context_for_user_copies_the_tenant_and_is_not_system():
    user = UserContext(user_id="u1", tenant_id="tenant-a", roles=frozenset({Role.USER}))

    context = RetrievalContext.for_user(user)

    assert context.tenant_id == "tenant-a"
    assert context.is_system is False


def test_retrieval_context_system_has_no_tenant_but_is_explicitly_privileged():
    context = RetrievalContext.system()

    assert context.tenant_id is None
    assert context.is_system is True


def test_retrieval_context_is_a_distinct_type_from_user_context():
    """Section 9's explicit requirement: RetrievalContext and UserContext
    are deliberately separate types, not one type doing double duty.
    """
    user = UserContext(user_id="u1", tenant_id="t1", roles=frozenset({Role.USER}))

    assert type(user) is not type(RetrievalContext.for_user(user))


def test_retrieval_context_is_frozen():
    context = RetrievalContext(tenant_id="t1")
    with pytest.raises(Exception):
        context.tenant_id = "t2"
