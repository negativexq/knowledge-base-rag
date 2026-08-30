import json
from types import SimpleNamespace

import pytest

from app.evaluation.index_validation import (
    EvaluationIndexMismatchError,
    validate_evaluation_index,
)
from app.ingestion.qdrant_store import VECTOR_NAME


class _MissingCollection:
    def collection_exists(self, collection):
        return False


class _CollectionMissingRequiredSource:
    def collection_exists(self, collection):
        return True

    def get_collection(self, collection):
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={VECTOR_NAME: SimpleNamespace(size=1024)},
                )
            )
        )

    def scroll(self, **kwargs):
        return [SimpleNamespace(payload={"source_id": "wrong-source", "tenant_id": "tenant"})], None


def test_evaluation_benchmark_fails_closed_when_collection_is_missing(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": []}), encoding="utf-8")
    validation = tmp_path / "index-validation.json"
    validation.write_text(
        json.dumps({"collection": "kb_eval", "corpus_fingerprint": "fp", "source_count": 0}),
        encoding="utf-8",
    )

    with pytest.raises(EvaluationIndexMismatchError, match="does not exist"):
        validate_evaluation_index(
            _MissingCollection(),
            "kb_eval",
            manifest,
            validation,
            "fp",
        )


def test_evaluation_benchmark_fails_closed_when_required_source_is_not_indexed(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"documents": [{"source_id": "required-source"}]}), encoding="utf-8"
    )
    validation = tmp_path / "index-validation.json"
    validation.write_text(
        json.dumps({"collection": "kb_eval", "corpus_fingerprint": "fp", "source_count": 1}),
        encoding="utf-8",
    )

    with pytest.raises(EvaluationIndexMismatchError, match="indexed sources do not match"):
        validate_evaluation_index(
            _CollectionMissingRequiredSource(),
            "kb_eval",
            manifest,
            validation,
            "fp",
        )
