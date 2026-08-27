from app.evaluation.phase55_decision import (
    changed_queries,
    cross_lingual_membership,
    family_impact,
    ndcg_breakdown,
    numerator_denominator,
)


def _record(query_id, family, category="cross_lingual", pair="tr->en", expected=None, ranked=None):
    return {
        "query_id": query_id,
        "case_family": family,
        "category": category,
        "query_language": "tr",
        "evidence_language": "en",
        "language_pair": pair,
        "tenant_id": "tenant-a",
        "expected_source_ids": expected or ["gold"],
        "candidate_source_ids": ranked or ["gold"],
        "ranked_source_ids": ranked or ["gold"],
    }


def _payload(k20, k15):
    return {
        "results": [
            {"candidate_k": 20, "records": k20},
            {"candidate_k": 15, "records": k15},
        ]
    }


def test_slice_numerator_denominator_is_explicit():
    rows = [_record("q1", "f"), _record("q2", "f", ranked=["other"])]

    assert numerator_denominator(rows) == {
        "record_count": 2,
        "eligible_count": 2,
        "numerator": 1,
        "denominator": 2,
        "recall_at_5": 0.5,
    }


def test_cross_lingual_membership_is_category_scoped():
    k20 = [_record("tr", "f", pair="tr->en"), _record("en", "g", pair="en->tr")]
    k15 = [_record("tr", "f", pair="tr->en", ranked=["other"]), _record("en", "g", pair="en->tr")]
    membership = cross_lingual_membership(_payload(k20, k15))

    assert membership["member_count"] == 2
    assert membership["language_pair_groups"]["tr->en"]["k20"]["numerator"] == 1
    assert membership["language_pair_groups"]["tr->en"]["k15"]["numerator"] == 0


def test_changed_query_directions_are_classified():
    k20 = [_record("lost", "f"), _record("gain", "g", ranked=["other"])]
    k15 = [_record("lost", "f", ranked=["other"]), _record("gain", "g")]
    changed = changed_queries(_payload(k20, k15))

    assert [item["query_id"] for item in changed["k20_hit_k15_miss"]] == ["lost"]
    assert [item["query_id"] for item in changed["k20_miss_k15_hit"]] == ["gain"]


def test_family_impact_averages_changed_family_members():
    k20 = [_record("q1", "family"), _record("q2", "family", ranked=["other"])]
    k15 = [_record("q1", "family", ranked=["other"]), _record("q2", "family", ranked=["other"])]
    payload = _payload(k20, k15)
    changed = changed_queries(payload)
    impact = family_impact(payload, changed)

    assert impact[0]["family_query_count"] == 2
    assert impact[0]["k20_family_recall_at_5"] == 0.5
    assert impact[0]["k15_family_recall_at_5"] == 0.0


def test_ndcg_breakdown_is_bounded_and_deduplicates_sources():
    breakdown = ndcg_breakdown(_record("q", "f", ranked=["gold", "gold", "other"]))

    assert breakdown["unique_ranked_top5"] == ["gold", "other"]
    assert breakdown["ndcg_at_5"] == 1.0
