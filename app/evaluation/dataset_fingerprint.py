import hashlib
import json
from typing import Any


def golden_set_fingerprint(questions: list[dict]) -> str:
    """Deterministic SHA-256 digest of a golden question set's content —
    NOT its file's on-disk bytes (which could differ in whitespace/key
    order across identical logical content), but the actual (id, query,
    query_lang, content_lang, expected_locations, difficulty) tuples,
    sorted by id and JSON-serialized with sort_keys=True. Sprint 21's
    reason to exist: proving two independent benchmark runs (this
    sprint's multi-run stability study, or a rerun months later) really
    used the IDENTICAL evaluation set, not just a file with the same
    name.
    """
    canonical = [
        {
            "id": q["id"],
            "query": q["query"],
            "query_lang": q["query_lang"],
            "content_lang": q.get("content_lang"),
            "expected_locations": q.get("expected_locations", []),
            "difficulty": q.get("difficulty"),
        }
        for q in sorted(questions, key=lambda q: q["id"])
    ]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def corpus_fingerprint(documents: dict[str, str]) -> str:
    """Deterministic SHA-256 digest of the benchmark corpus's real text
    content — documents is {filename: raw_text_content}, built from the
    SAME tests/fixtures/golden_*.py functions the benchmark scripts use
    to build the corpus, so this fingerprint changes if and only if the
    actual corpus content changes.
    """
    canonical = json.dumps(dict(sorted(documents.items())), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluation_corpus_fingerprint(documents: list[dict[str, Any]]) -> str:
    """Fingerprint an evaluation corpus's identity, metadata, and text.

    This includes tenant, language, content type, and relative path so a
    corpus can be reproduced without depending on a live index or model
    output.
    """
    canonical = [
        {
            "source_id": document["source_id"],
            "path": document["path"],
            "tenant_id": document["tenant_id"],
            "language": document["language"],
            "content_type": document["content_type"],
            "text": document["text"],
        }
        for document in sorted(documents, key=lambda item: item["source_id"])
    ]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluation_dataset_fingerprint(questions: list[dict[str, Any]]) -> str:
    """Fingerprint every evaluator-owned field in a v2 golden dataset."""
    canonical = [question for question in sorted(questions, key=lambda item: item["id"])]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
