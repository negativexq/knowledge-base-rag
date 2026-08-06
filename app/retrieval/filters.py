from qdrant_client.http import models as qmodels


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
