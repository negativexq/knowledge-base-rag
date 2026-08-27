import json

import pytest

from app.evaluation.index_validation import (
    EvaluationIndexMismatchError,
    validate_evaluation_index,
)


class _MissingCollection:
    def collection_exists(self, collection):
        return False


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
