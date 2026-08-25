import pytest
from qdrant_client.http import models as qmodels

from app.retrieval.filters import (
    MissingTenantContextError,
    build_acl_filter,
    build_filter,
    combine_filters,
)
from app.security.models import RetrievalContext


def test_build_acl_filter_for_a_tenant_scoped_context():
    context = RetrievalContext(tenant_id="tenant-a")

    acl_filter = build_acl_filter(context)

    assert acl_filter == qmodels.Filter(
        must=[qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value="tenant-a"))]
    )


def test_build_acl_filter_for_system_context_returns_none():
    context = RetrievalContext.system()

    assert build_acl_filter(context) is None


def test_build_acl_filter_fails_closed_when_tenant_missing_and_not_system():
    """Invariant 2/8: there is no "return everything" fallback — a
    context that isn't explicitly system but has no tenant_id must raise,
    never silently build an unrestricted filter.
    """
    context = RetrievalContext(tenant_id=None, is_system=False)

    with pytest.raises(MissingTenantContextError):
        build_acl_filter(context)


def test_build_acl_filter_fails_closed_for_empty_string_tenant():
    context = RetrievalContext(tenant_id="", is_system=False)

    with pytest.raises(MissingTenantContextError):
        build_acl_filter(context)


def test_combine_filters_ands_acl_and_user_filter_together():
    acl = build_acl_filter(RetrievalContext(tenant_id="tenant-a"))
    user = build_filter(source_types=["filesystem"])

    combined = combine_filters(acl, user)

    assert combined == qmodels.Filter(must=[acl, user])


def test_combine_filters_returns_acl_alone_when_no_user_filter():
    acl = build_acl_filter(RetrievalContext(tenant_id="tenant-a"))

    assert combine_filters(acl, None) == acl


def test_combine_filters_returns_user_filter_alone_for_a_system_context():
    user = build_filter(source_types=["filesystem"])

    assert combine_filters(None, user) == user


def test_combine_filters_returns_none_only_when_both_are_none():
    assert combine_filters(None, None) is None


def test_a_malicious_user_filter_naming_another_tenant_only_narrows_never_widens():
    """The concrete proof behind "user filters cannot weaken ACL":
    ANDing a caller-supplied tenant_id=B condition onto a real ACL of
    tenant_id=A produces a filter that can never match ANY point (no
    point has both tenant_id values) — it does not fall back to "ACL
    only" or somehow select tenant B instead.
    """
    acl = build_acl_filter(RetrievalContext(tenant_id="tenant-a"))
    malicious_user_filter = qmodels.Filter(
        must=[qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value="tenant-b"))]
    )

    combined = combine_filters(acl, malicious_user_filter)

    assert combined == qmodels.Filter(must=[acl, malicious_user_filter])
    assert combined != acl  # the ACL was not silently dropped/overridden
