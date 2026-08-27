from scripts.benchmark_query_scope_boundary import compact_scope_metadata


def test_compact_scope_metadata_keeps_only_runtime_safe_applicability_fields():
    record = {
        "authorized_top5": [
            {
                "chunk_id": "chunk-1",
                "source_id": "source-1",
                "content": "secret evidence",
                "score": 0.9,
                "title": "Returns policy",
                "authority_role": "canonical",
                "authority_scope": "customer",
                "expected_source_ids": ["source-1"],
            },
            {
                "chunk_id": "chunk-2",
                "source_id": "source-2",
                "content": "more evidence",
                "title": "Returns policy",
                "authority_role": "canonical",
                "authority_scope": "customer",
            },
        ]
    }

    assert compact_scope_metadata(record) == [
        {
            "authority_role": "canonical",
            "authority_scope": "customer",
            "title": "Returns policy",
        }
    ]


def test_compact_scope_metadata_falls_back_to_empty_when_metadata_is_unavailable():
    assert compact_scope_metadata({"authorized_top5": [{"chunk_id": "chunk-1"}]}) == []
