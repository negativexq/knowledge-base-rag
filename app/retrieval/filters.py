from qdrant_client.http import models as qmodels

from app.security.models import RetrievalContext


class MissingTenantContextError(Exception):
    """Raised by build_acl_filter when a non-system RetrievalContext has
    no tenant_id — fail-closed (Sprint 23 section 8): there is no
    "return everything" fallback. A caller that legitimately needs
    cross-tenant access must construct RetrievalContext.system()
    explicitly; this is never raised for that case.
    """


def build_acl_filter(context: RetrievalContext) -> qmodels.Filter | None:
    """The MANDATORY, server-owned authorization filter — completely
    separate from build_filter() below (user-supplied retrieval
    filters). Returns None only for an EXPLICIT system context
    (RetrievalContext.system()); every other context must resolve to a
    real `tenant_id == ...` condition, or this raises rather than
    silently building an unrestricted filter. See
    app/retrieval/search.py::search(), the server-owned context used for
    the post-retrieval ACL check before reranking.
    """
    if context.is_system:
        return None
    if not context.tenant_id:
        raise MissingTenantContextError(
            "RetrievalContext has no tenant_id and is not a system context — refusing to "
            "build an unrestricted retrieval filter. Use RetrievalContext.system() if "
            "cross-tenant access is genuinely intended."
        )
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="tenant_id", match=qmodels.MatchValue(value=context.tenant_id)
            )
        ]
    )


def combine_filters(
    acl_filter: qmodels.Filter | None, user_filter: qmodels.Filter | None
) -> qmodels.Filter | None:
    """ACL AND user-supplied filters — never OR, never a caller-provided
    override of the ACL half. Qdrant filters nest natively (a Filter can
    appear inside another Filter's `must` list), so this doesn't need to
    merge individual conditions — just AND the two filters together
    as-is. Returns whichever single filter is non-None if only one is
    present, and None only when BOTH are None (i.e. a system context
    with no user filters — genuinely unrestricted, by explicit design).
    """
    if acl_filter is not None and user_filter is not None:
        return qmodels.Filter(must=[acl_filter, user_filter])
    return acl_filter or user_filter


def filter_authorized_candidates(candidates: list, context: RetrievalContext) -> list:
    """Apply the server-owned tenant boundary before reranking.

    The raw candidate count is safe to retain as an integer, but unauthorized
    result objects are discarded here and never returned downstream.
    """
    if context.is_system:
        return list(candidates)
    return [
        candidate
        for candidate in candidates
        if candidate.payload.get("tenant_id") == context.tenant_id
    ]


def build_filter(
    doc_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    page_numbers: list[int] | None = None,
) -> qmodels.Filter | None:
    """Build a Qdrant payload filter from the chunk metadata fields (doc_id,
    source_type, source_id, page_number). Fields are AND-ed together; values
    within a field are OR-ed (MatchAny). Returns None if nothing was given,
    so callers can pass it straight through without a "no filter" special
    case.
    """
    conditions: list[qmodels.FieldCondition] = []

    if doc_ids:
        conditions.append(qmodels.FieldCondition(key="doc_id", match=qmodels.MatchAny(any=doc_ids)))
    if source_types:
        conditions.append(
            qmodels.FieldCondition(key="source_type", match=qmodels.MatchAny(any=source_types))
        )
    if source_ids:
        conditions.append(
            qmodels.FieldCondition(key="source_id", match=qmodels.MatchAny(any=source_ids))
        )
    if page_numbers:
        conditions.append(
            qmodels.FieldCondition(key="page_number", match=qmodels.MatchAny(any=page_numbers))
        )

    if not conditions:
        return None

    return qmodels.Filter(must=conditions)
