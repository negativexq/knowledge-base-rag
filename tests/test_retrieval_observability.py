from app.retrieval.retrieval_observability import serialize_retrieval_observation


def test_retrieval_observation_is_ranked_and_does_not_persist_plain_text():
    result = serialize_retrieval_observation(
        [{"chunk_id": "c1", "source_id": "s1", "text": "secret text", "score": 0.9}],
        [],
        [],
    )
    assert result["authorized_top20"][0]["rank"] == 1
    assert result["authorized_top20"][0]["text_hash"]
    assert "secret text" not in str(result)
