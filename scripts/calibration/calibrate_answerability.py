"""Fit and confirm small, safety-first answerability policies.

Development is the only fitting/threshold-selection split. Calibration is
read only after a candidate is locked. Frozen test is not loaded by this
module. This produces policy evidence for Phase 6C; it does not change
runtime behavior.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
FEATURE_DIR = ROOT / "artifacts/phase-6/answerability-features"
DEFAULT_DEVELOPMENT = FEATURE_DIR / "development.jsonl"
DEFAULT_CALIBRATION = FEATURE_DIR / "calibration.jsonl"
OUTPUT_DIR = ROOT / "artifacts/phase-6/calibration"

ALL_FEATURES = (
    "authorized_candidate_count",
    "reranked_count",
    "top1_score",
    "top2_score",
    "top3_score",
    "top1_top2_margin",
    "top1_top3_margin",
    "mean_top3_score",
    "mean_top5_score",
    "min_top5_score",
    "max_top5_score",
    "std_top5_score",
    "distinct_source_count_top5",
    "distinct_document_count_top5",
    "duplicate_source_chunk_count_top5",
    "source_score_concentration",
)
OPTIONAL_FEATURES = (
    "pre_acl_candidate_count",
    "top1_fused_rank",
    "top1_dense_rank",
    "top1_sparse_rank",
    "dense_sparse_agreement",
    "fused_rerank_agreement",
)
LEAKAGE_FIELDS = (
    "expected_source_ids",
    "required_source_ids",
    "answerability_label",
    "category",
    "case_family",
    "query_id",
    "split",
    "tenant",
    "query_language",
    "evidence_language",
    "language_pair",
)
ABSTAIN_REASONS = (
    "NO_RETRIEVAL_CANDIDATES",
    "NO_AUTHORIZED_EVIDENCE",
    "EMPTY_RERANK_RESULT",
)


def load_records(path: Path, expected_split: str) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not records or any(record["split"] != expected_split for record in records):
        raise ValueError(f"feature artifact is empty or has the wrong split: {path}")
    return records


def validate_family_separation(development: list[dict], calibration: list[dict]) -> None:
    development_families = {record["case_family"] for record in development}
    calibration_families = {record["case_family"] for record in calibration}
    overlap = development_families & calibration_families
    if overlap:
        raise ValueError(f"development/calibration case-family leakage: {sorted(overlap)}")


def target(record: dict) -> int:
    """Binary safety target: 1 means ABSTAIN, 0 means ANSWER."""
    return 0 if record["answerability_label"] == "answerable" else 1


def safety_prediction(record: dict) -> str | None:
    if record["deterministic_reason"] in ABSTAIN_REASONS:
        return "ABSTAIN"
    return None


def usable_features(development: list[dict], calibration: list[dict]) -> list[str]:
    usable = []
    for field in ALL_FEATURES:
        if all(record["features"].get(field) is not None for record in development + calibration):
            usable.append(field)
    if not usable:
        raise ValueError("no non-null retrieval-derived features are available")
    return usable


def unavailable_features(
    development: list[dict], calibration: list[dict], usable: list[str]
) -> list[str]:
    return [
        field
        for field in (*ALL_FEATURES, *OPTIONAL_FEATURES)
        if field not in usable
        and not all(
            record["features"].get(field) is not None
            for record in development + calibration
        )
    ]


def _values(records: list[dict], feature: str) -> np.ndarray:
    return np.array([float(record["features"][feature]) for record in records], dtype=float)


def _finite_thresholds(values: np.ndarray) -> list[float]:
    unique = sorted(set(float(value) for value in values))
    if not unique:
        raise ValueError("cannot build thresholds from an empty feature")
    thresholds = {math.nextafter(unique[0], -math.inf), math.nextafter(unique[-1], math.inf)}
    thresholds.update(unique)
    return sorted(thresholds)


def _raw_abstain_score(feature_values: np.ndarray) -> np.ndarray:
    # Higher raw values generally indicate stronger evidence for these
    # retrieval signals; invert them so larger values consistently mean
    # stronger abstention evidence for AUROC/AUPRC reporting.
    return -feature_values


def _predict_from_threshold(values: np.ndarray, threshold: float) -> np.ndarray:
    return (values < threshold).astype(int)


def _confusion(
    records: list[dict], abstain_predictions: np.ndarray
) -> dict[str, int | float | None]:
    truth = np.array([target(record) for record in records], dtype=int)
    correct_abstain = int(((truth == 1) & (abstain_predictions == 1)).sum())
    false_abstain = int(((truth == 0) & (abstain_predictions == 1)).sum())
    correct_answer = int(((truth == 0) & (abstain_predictions == 0)).sum())
    false_answer = int(((truth == 1) & (abstain_predictions == 0)).sum())
    true_abstain = int((truth == 1).sum())
    answerable = int((truth == 0).sum())
    predicted_abstain = int((abstain_predictions == 1).sum())
    accuracy = (correct_answer + correct_abstain) / len(records) if records else None
    balanced_accuracy = (
        ((correct_answer / answerable) if answerable else 0.0)
        + ((correct_abstain / true_abstain) if true_abstain else 0.0)
    ) / 2 if records else None
    abstention_precision = correct_abstain / predicted_abstain if predicted_abstain else 0.0
    abstention_recall = correct_abstain / true_abstain if true_abstain else 0.0
    abstention_f1 = (
        2 * abstention_precision * abstention_recall / (abstention_precision + abstention_recall)
        if abstention_precision + abstention_recall
        else 0.0
    )
    return {
        "correct_answer": correct_answer,
        "false_answer": false_answer,
        "correct_abstain": correct_abstain,
        "false_abstain": false_abstain,
        "true_abstain": true_abstain,
        "answerable_count": answerable,
        "predicted_abstain": predicted_abstain,
        "false_answer_rate": false_answer / true_abstain if true_abstain else 0.0,
        "false_abstention_rate": false_abstain / answerable if answerable else 0.0,
        "answerable_coverage": correct_answer / answerable if answerable else 0.0,
        "abstention_precision": abstention_precision,
        "abstention_recall": abstention_recall,
        "abstention_f1": abstention_f1,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        # Positive class is ABSTAIN: TP=correct_abstain, FP=false_abstain.
        "tp": correct_abstain,
        "fp": false_abstain,
        "tn": correct_answer,
        "fn": false_answer,
    }


def _ranking_metrics(records: list[dict], abstain_scores: np.ndarray) -> dict[str, float | None]:
    truth = np.array([target(record) for record in records], dtype=int)
    if len(set(truth.tolist())) < 2:
        return {"auroc": None, "auprc": None}
    return {
        "auroc": round(float(roc_auc_score(truth, abstain_scores)), 6),
        "auprc": round(float(average_precision_score(truth, abstain_scores)), 6),
    }


def _probability_metrics(records: list[dict], probabilities: np.ndarray) -> dict[str, float | None]:
    truth = np.array([target(record) for record in records], dtype=float)
    brier = float(np.mean((probabilities - truth) ** 2))
    ece = 0.0
    for lower in np.linspace(0.0, 1.0, 11)[:-1]:
        upper = lower + 0.1
        mask = (probabilities >= lower) & (
            probabilities <= upper if upper == 1.0 else probabilities < upper
        )
        if mask.any():
            ece += mask.mean() * abs(float(probabilities[mask].mean()) - float(truth[mask].mean()))
    return {"brier_score": round(brier, 6), "ece_10_bin": round(float(ece), 6)}


def evaluate_predictions(
    records: list[dict], abstain_predictions: np.ndarray, abstain_scores: np.ndarray | None = None,
    probabilities: np.ndarray | None = None,
) -> dict[str, Any]:
    result = _confusion(records, abstain_predictions)
    if abstain_scores is not None:
        result.update(_ranking_metrics(records, abstain_scores))
    else:
        result.update({"auroc": None, "auprc": None})
    if probabilities is not None:
        result.update(_probability_metrics(records, probabilities))
    return result


def family_metrics(
    records: list[dict], abstain_predictions: np.ndarray
) -> dict[str, float | int | None]:
    """Macro-average query outcomes inside each case family first."""
    families = sorted({record["case_family"] for record in records})
    family_rows = []
    for family in families:
        indexes = [
            index
            for index, record in enumerate(records)
            if record["case_family"] == family
        ]
        family_records = [records[index] for index in indexes]
        family_result = _confusion(
            family_records,
            abstain_predictions[indexes],
        )
        family_result["correct_answer_rate"] = (
            family_result["correct_answer"] / family_result["answerable_count"]
            if family_result["answerable_count"]
            else 0.0
        )
        family_result["correct_abstain_rate"] = (
            family_result["correct_abstain"] / family_result["true_abstain"]
            if family_result["true_abstain"]
            else 0.0
        )
        family_rows.append(family_result)

    def mean(field: str, eligible: Callable[[dict], bool] | None = None) -> float:
        rows = [row for row in family_rows if eligible is None or eligible(row)]
        return (
            round(float(np.mean([float(row[field]) for row in rows])), 6)
            if rows
            else 0.0
        )

    return {
        "family_count": len(family_rows),
        "answerable_coverage": mean(
            "answerable_coverage", lambda row: row["answerable_count"] > 0
        ),
        "false_answer_rate": mean(
            "false_answer_rate", lambda row: row["true_abstain"] > 0
        ),
        "false_abstention_rate": mean(
            "false_abstention_rate", lambda row: row["answerable_count"] > 0
        ),
        "correct_answer_rate": mean(
            "correct_answer_rate", lambda row: row["answerable_count"] > 0
        ),
        "correct_abstain_rate": mean(
            "correct_abstain_rate", lambda row: row["true_abstain"] > 0
        ),
        "false_answer_families": sum(
            row["false_answer"] > 0 for row in family_rows
        ),
        "false_abstention_families": sum(
            row["false_abstain"] > 0 for row in family_rows
        ),
    }


def _candidate_thresholds(
    records: list[dict], score_fn: Callable[[list[dict]], np.ndarray]
) -> list[float]:
    return _finite_thresholds(score_fn(records))


def _select_development_candidate(candidates: list[dict]) -> dict:
    # False-answer minimization is primary. Require at least one ANSWER on
    # development so abstain-on-everything cannot be selected trivially.
    nontrivial = [candidate for candidate in candidates if candidate["dev"]["correct_answer"] > 0]
    if not nontrivial:
        raise ValueError("no non-trivial candidate answers any development record")
    return min(
        nontrivial,
        key=lambda candidate: (
            candidate["dev"]["false_answer"],
            -candidate["dev"]["answerable_coverage"],
            candidate["complexity_rank"],
            candidate["method"],
        ),
    )


def _slice_results(
    records: list[dict], predict: Callable[[list[dict]], tuple[np.ndarray, np.ndarray | None]],
    probability_output: bool,
) -> dict[str, dict[str, Any]]:
    dimensions = ("category", "query_language", "evidence_language", "language_pair", "tenant")
    output: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        field = dimension if dimension != "tenant" else "tenant"
        groups = sorted({str(record[field]) for record in records})
        output[dimension] = {}
        for group in groups:
            selected = [
                record
                for record in records
                if str(record[dimension if dimension != "tenant" else "tenant"]) == group
            ]
            predictions, probabilities = predict(selected)
            predictions = _apply_safety_override(selected, predictions)
            output[dimension][group] = {
                "n": len(selected),
                **evaluate_predictions(
                    selected,
                    predictions,
                    probabilities,
                    probabilities if probability_output else None,
                ),
            }
    return output


def _model_pipeline(features: list[str]) -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    random_state=0,
                    solver="liblinear",
                    max_iter=1000,
                ),
            ),
        ]
    )


def _fit_logistic(
    development: list[dict], features: list[str]
) -> tuple[Pipeline, np.ndarray, float]:
    model = _model_pipeline(features)
    x = np.array([[record["features"][feature] for feature in features] for record in development])
    y = np.array([target(record) for record in development])
    model.fit(x, y)
    probabilities = model.predict_proba(x)[:, 1]
    return model, probabilities, float(probabilities.min())


def _model_predictor(model: Pipeline, features: list[str], threshold: float):
    def predict(records: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        x = np.array([[record["features"][feature] for feature in features] for record in records])
        probabilities = model.predict_proba(x)[:, 1]
        return (probabilities >= threshold).astype(int), probabilities

    return predict


def _single_predictor(feature: str, threshold: float):
    def predict(records: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        values = _values(records, feature)
        probabilities = _raw_abstain_score(values)
        return _predict_from_threshold(values, threshold), probabilities

    return predict


def _make_single_candidates(
    development: list[dict], feature: str, complexity_rank: int
) -> list[dict]:
    values = _values(development, feature)
    candidates = []
    for threshold in _finite_thresholds(values):
        predictions = _apply_safety_override(
            development,
            _predict_from_threshold(values, threshold),
        )
        candidates.append(
            {
                "method": feature,
                "features": [feature],
                "threshold": threshold,
                "complexity_rank": complexity_rank,
                "predictor_kind": "single_feature",
                "dev": evaluate_predictions(development, predictions, _raw_abstain_score(values)),
            }
        )
    return candidates


def _make_logistic_candidates(
    development: list[dict], features: list[str], complexity_rank: int
) -> list[dict]:
    model, probabilities, _ = _fit_logistic(development, features)
    candidates = []
    for threshold in _finite_thresholds(probabilities):
        predictions = _apply_safety_override(
            development,
            (probabilities >= threshold).astype(int),
        )
        candidates.append(
            {
                "method": "logistic_" + "_".join(features),
                "features": features,
                "threshold": threshold,
                "complexity_rank": complexity_rank,
                "predictor_kind": "logistic",
                "dev": evaluate_predictions(
                    development,
                    predictions,
                    probabilities,
                    probabilities,
                ),
                "model": model,
            }
        )
    return candidates


def _serialize_model(model: Pipeline, features: list[str], threshold: float, output: Path) -> None:
    scaler = model.named_steps["scaler"]
    classifier = model.named_steps["classifier"]
    output.write_text(
        json.dumps(
            {
                "schema_version": "phase-6b-logistic-v1",
                "feature_order": features,
                "scaler_mean": [round(float(value), 12) for value in scaler.mean_],
                "scaler_scale": [round(float(value), 12) for value in scaler.scale_],
                "coefficients": [round(float(value), 12) for value in classifier.coef_[0]],
                "intercept": round(float(classifier.intercept_[0]), 12),
                "threshold": round(threshold, 12),
                "positive_class": "ABSTAIN",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _distribution(records: list[dict], feature: str) -> dict[str, Any]:
    values = _values(records, feature)
    return {
        "n": len(values),
        "mean": round(float(values.mean()), 6),
        "std": round(float(values.std()), 6),
        "min": round(float(values.min()), 6),
        "p10": round(float(np.percentile(values, 10)), 6),
        "p25": round(float(np.percentile(values, 25)), 6),
        "median": round(float(np.median(values)), 6),
        "p75": round(float(np.percentile(values, 75)), 6),
        "p90": round(float(np.percentile(values, 90)), 6),
        "p95": round(float(np.percentile(values, 95)), 6),
        "max": round(float(values.max()), 6),
    }


def build_distributions(records: list[dict], features: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    groups = {
        "binary": {
            "ANSWER": [record for record in records if target(record) == 0],
            "ABSTAIN": [record for record in records if target(record) == 1],
        },
        "original": {
            label: [record for record in records if record["answerability_label"] == label]
            for label in ("answerable", "unanswerable", "ambiguous")
        },
    }
    for dimension, selected_groups in groups.items():
        output[dimension] = {
            group: {feature: _distribution(selected, feature) for feature in features}
            for group, selected in selected_groups.items()
        }
    return output


def write_distribution_csv(distributions: dict, path: Path) -> None:
    fields = (
        "split",
        "label_space",
        "group",
        "feature",
        "n",
        "mean",
        "std",
        "min",
        "p10",
        "p25",
        "median",
        "p75",
        "p90",
        "p95",
        "max",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for split, split_distributions in distributions.items():
            for label_space, groups in split_distributions.items():
                for group, features in groups.items():
                    for feature, values in features.items():
                        writer.writerow(
                            {
                                "split": split,
                                "label_space": label_space,
                                "group": group,
                                "feature": feature,
                                **values,
                            }
                        )


def _curve_rows(
    method: str,
    records: list[dict],
    scores: np.ndarray,
    thresholds: list[float],
    direction: str,
) -> list[dict]:
    rows = []
    for threshold in thresholds:
        if direction == "raw":
            predictions = _predict_from_threshold(scores, threshold)
            abstain_score = _raw_abstain_score(scores)
        else:
            predictions = (scores >= threshold).astype(int)
            abstain_score = scores
        predictions = _apply_safety_override(records, predictions)
        metrics = evaluate_predictions(records, predictions, abstain_score)
        true_abstain = metrics["true_abstain"]
        answerable = metrics["answerable_count"]
        rows.append(
            {
                "method": method,
                "threshold": threshold,
                "tpr_abstain": metrics["correct_abstain"] / true_abstain if true_abstain else 0.0,
                "fpr_abstain": metrics["false_abstain"] / answerable if answerable else 0.0,
                "precision_abstain": metrics["abstention_precision"],
                "recall_abstain": metrics["abstention_recall"],
                "coverage": metrics["answerable_coverage"],
                "false_answer_rate": metrics["false_answer_rate"],
                "split": "development",
            }
        )
    return rows


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _load_metadata(path: Path) -> dict:
    return json.loads(path.with_name(f"{path.stem}-summary.json").read_text(encoding="utf-8"))


def _validate_reference_config(config: dict) -> None:
    required = {
        "candidate_k": 20,
        "top_n": 5,
        "embedding_dimension": 1024,
        "retrieval_method": "BM25 + dense + RRF",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "generation_invoked": False,
    }
    for key, expected in required.items():
        if config.get(key) != expected:
            raise ValueError(
                f"Phase 6B reference config mismatch for {key}: "
                f"expected {expected!r}, got {config.get(key)!r}"
            )


def _apply_safety_override(records: list[dict], predictions: np.ndarray) -> np.ndarray:
    overridden = predictions.copy()
    for index, record in enumerate(records):
        if record["deterministic_reason"] in ABSTAIN_REASONS:
            overridden[index] = 1
    return overridden


def _result_for_candidate(candidate: dict, records: list[dict], model: Pipeline | None) -> dict:
    if candidate["predictor_kind"] == "single_feature":
        predictor = _single_predictor(candidate["features"][0], candidate["threshold"])
    else:
        if model is None:
            raise ValueError("logistic candidate is missing its fitted model")
        predictor = _model_predictor(model, candidate["features"], candidate["threshold"])
    predictions, probabilities = predictor(records)
    predictions = _apply_safety_override(records, predictions)
    result = evaluate_predictions(
        records,
        predictions,
        probabilities,
        probabilities if model else None,
    )
    result["family"] = family_metrics(records, predictions)
    model_probability = model is not None
    return {
        "method": candidate["method"],
        "features": candidate["features"],
        "threshold": round(candidate["threshold"], 12),
        "predictor_kind": candidate["predictor_kind"],
        "metrics": result,
        "slices": _slice_results(records, predictor, model_probability),
    }


def _best_candidate_per_method(candidates: list[dict]) -> list[dict]:
    methods = sorted({candidate["method"] for candidate in candidates})
    best = []
    for method in methods:
        options = [candidate for candidate in candidates if candidate["method"] == method]
        best.append(_select_development_candidate(options))
    return best


def _pareto_frontier(rows: list[dict]) -> list[dict]:
    frontier = []
    for row in rows:
        dominated = any(
            other["false_answer_rate"] <= row["false_answer_rate"]
            and other["coverage"] >= row["coverage"]
            and (
                other["false_answer_rate"] < row["false_answer_rate"]
                or other["coverage"] > row["coverage"]
            )
            for other in rows
        )
        if not dominated:
            frontier.append(row)
    return sorted(
        frontier,
        key=lambda row: (row["false_answer_rate"], -row["coverage"], row["threshold"]),
    )


def _policy_status(calibration_result: dict) -> tuple[str, str]:
    metrics = calibration_result["metrics"]
    if metrics["false_answer"]:
        return "INCONCLUSIVE", "Calibration contains false answers."
    if not metrics["correct_answer"]:
        return "INCONCLUSIVE", "The candidate abstains on every calibration query."
    critical = (
        "hard_answerable",
        "cross_lingual",
        "multi_document",
        "version_conflict",
        "injection_bearing",
    )
    zero_coverage = [
        category
        for category in critical
        if (
            calibration_result["slices"]["category"].get(category, {}).get(
                "answerable_count", 0
            )
            > 0
            and calibration_result["slices"]["category"][category][
                "answerable_coverage"
            ]
            == 0
        )
    ]
    if zero_coverage:
        return (
            "INCONCLUSIVE",
            "Zero answerable coverage in critical slices: "
            + ", ".join(zero_coverage)
            + ".",
        )
    return "LOCK", "No false answers and non-zero coverage across critical slices."


def run() -> dict:
    development = load_records(DEFAULT_DEVELOPMENT, "development")
    calibration = load_records(DEFAULT_CALIBRATION, "calibration")
    validate_family_separation(development, calibration)
    development_metadata = _load_metadata(DEFAULT_DEVELOPMENT)
    calibration_metadata = _load_metadata(DEFAULT_CALIBRATION)
    if development_metadata["config"] != calibration_metadata["config"]:
        raise ValueError("development/calibration feature config mismatch")
    config = development_metadata["config"]
    _validate_reference_config(config)
    features = usable_features(development, calibration)
    unavailable = unavailable_features(development, calibration, features)

    candidate_pool: list[dict] = []
    candidate_pool.extend(_make_single_candidates(development, "top1_score", 0))
    candidate_pool.extend(_make_single_candidates(development, "top1_top2_margin", 1))
    candidate_pool.extend(_make_single_candidates(development, "mean_top3_score", 2))
    ablations = [
        ("top1_score", ["top1_score"], 3),
        ("top1_margin", ["top1_score", "top1_top2_margin"], 4),
        ("top1_margin_mean_top3", ["top1_score", "top1_top2_margin", "mean_top3_score"], 5),
        ("full_compact", features, 6),
    ]
    fitted_models: dict[str, Pipeline] = {}
    for _name, model_features, complexity_rank in ablations:
        candidates = _make_logistic_candidates(development, model_features, complexity_rank)
        candidate_pool.extend(candidates)
        if candidates:
            fitted_models[candidates[0]["method"]] = candidates[0]["model"]

    selected = _select_development_candidate(candidate_pool)
    selected_model = fitted_models.get(selected["method"])
    development_result = _result_for_candidate(selected, development, selected_model)
    calibration_result = _result_for_candidate(selected, calibration, selected_model)
    method_comparison = []
    for candidate in _best_candidate_per_method(candidate_pool):
        model = fitted_models.get(candidate["method"])
        confirmation = _result_for_candidate(candidate, calibration, model)
        method_comparison.append(
            {
                "method": candidate["method"],
                "features": candidate["features"],
                "threshold": round(candidate["threshold"], 12),
                "predictor_kind": candidate["predictor_kind"],
                "development": candidate["dev"],
                "calibration": confirmation["metrics"],
            }
        )

    threshold_rows = []
    for feature in ("top1_score", "top1_top2_margin", "mean_top3_score"):
        values = _values(development, feature)
        threshold_rows.extend(
            _curve_rows(feature, development, values, _finite_thresholds(values), "raw")
    )
    if selected_model is not None:
        x = np.array(
            [
                [record["features"][feature] for feature in selected["features"]]
                for record in development
            ]
        )
        probabilities = selected_model.predict_proba(x)[:, 1]
        threshold_rows.extend(
            _curve_rows(
                selected["method"],
                development,
                probabilities,
                _finite_thresholds(probabilities),
                "probability",
            )
        )
    for row in threshold_rows:
        row["threshold"] = round(float(row["threshold"]), 12)

    pareto = {}
    for feature in ("top1_score", "top1_top2_margin", "mean_top3_score"):
        feature_rows = [
            row
            for row in threshold_rows
            if row["method"] == feature and row["split"] == "development"
        ]
        pareto[feature] = _pareto_frontier(feature_rows)
    if selected_model is not None:
        method_rows = [
            row
            for row in threshold_rows
            if row["method"] == selected["method"] and row["split"] == "development"
        ]
        pareto[selected["method"]] = _pareto_frontier(method_rows)

    all_candidate_summaries = []
    for candidate in candidate_pool:
        summary = {
            "method": candidate["method"],
            "features": candidate["features"],
            "threshold": round(candidate["threshold"], 12),
            "predictor_kind": candidate["predictor_kind"],
            "complexity_rank": candidate["complexity_rank"],
            "development": candidate["dev"],
        }
        if candidate is selected:
            summary["selected"] = True
        all_candidate_summaries.append(summary)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "calibration-features.jsonl").write_text(
        DEFAULT_CALIBRATION.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    distributions = {
        "development": build_distributions(development, features),
        "calibration": build_distributions(calibration, features),
    }
    (OUTPUT_DIR / "feature-distributions.json").write_text(
        json.dumps(distributions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_distribution_csv(distributions, OUTPUT_DIR / "feature-distributions.csv")
    (OUTPUT_DIR / "candidate-methods.json").write_text(
        json.dumps(
            {
                "training_split": "development",
                "confirmation_split": "calibration",
                "leakage_fields_excluded": list(LEAKAGE_FIELDS),
                "feature_input_fields": features,
                "features_unavailable": unavailable,
                "candidates": all_candidate_summaries,
                "development_best_per_method": method_comparison,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "pareto-frontier.json").write_text(
        json.dumps(pareto, indent=2) + "\n", encoding="utf-8"
    )
    with (OUTPUT_DIR / "threshold-curves.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = (
            "method",
            "threshold",
            "tpr_abstain",
            "fpr_abstain",
            "precision_abstain",
            "recall_abstain",
            "coverage",
            "false_answer_rate",
            "split",
        )
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(threshold_rows)
    (OUTPUT_DIR / "development-results.json").write_text(
        json.dumps(
            {
                "selected": development_result,
                "candidates": all_candidate_summaries,
                "best_per_method": method_comparison,
                "family_leakage": {"overlap_count": 0},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "calibration-results.json").write_text(
        json.dumps(
            {
                "selected": calibration_result,
                "best_per_method": method_comparison,
                "family_leakage": {"overlap_count": 0},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "slice-results.json").write_text(
        json.dumps(
            {
                "development": development_result["slices"],
                "calibration": calibration_result["slices"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if selected_model is not None:
        _serialize_model(
            selected_model,
            selected["features"],
            selected["threshold"],
            OUTPUT_DIR / "model.json",
        )

    status, status_reason = _policy_status(calibration_result)
    policy = {
        "policy_version": "phase-6b-answerability-v1",
        "status": status,
        "status_reason": status_reason,
        "method": selected["method"] if status == "LOCK" else None,
        "features": selected["features"] if status == "LOCK" else [],
        "threshold": round(selected["threshold"], 12) if status == "LOCK" else None,
        "predictor_kind": selected["predictor_kind"] if status == "LOCK" else None,
        "positive_class": "ABSTAIN",
        "deterministic_abstain_reasons": list(ABSTAIN_REASONS),
        "training_split": "development",
        "confirmation_split": "calibration",
        "family_leakage": {
            "development_family_count": development_result["metrics"]["family"][
                "family_count"
            ],
            "calibration_family_count": calibration_result["metrics"]["family"][
                "family_count"
            ],
            "overlap_count": 0,
        },
        "frozen_test_used": False,
        "automatic_runtime_promotion": False,
        "corpus_fingerprint": config["corpus_fingerprint"],
        "dataset_fingerprint": config["dataset_fingerprint"],
        "collection": config["collection"],
        "candidate_k": config["candidate_k"],
        "top_n": config["top_n"],
        "feature_schema_version": "phase-6a-answerability-v1",
        "config_snapshot": config,
        "git_sha": _git_sha(),
    }
    (OUTPUT_DIR / "final-policy.json").write_text(
        json.dumps(policy, indent=2) + "\n", encoding="utf-8"
    )
    report = _build_report(
        policy,
        selected,
        development_result,
        calibration_result,
        development_metadata,
        calibration_metadata,
        features,
        unavailable,
    )
    (OUTPUT_DIR / "calibration-report.md").write_text(report, encoding="utf-8")
    return policy


def _build_report(
    policy: dict,
    selected: dict,
    development: dict,
    calibration: dict,
    development_metadata: dict,
    calibration_metadata: dict,
    features: list[str],
    unavailable: list[str],
) -> str:
    dm = development["metrics"]
    cm = calibration["metrics"]
    selected_features = ", ".join(selected["features"])
    false_answers = (
        f"{dm['false_answer']}/{dm['true_abstain']}"
        f" ({cm['false_answer']}/{cm['true_abstain']} calibration)"
    )
    false_abstentions = (
        f"{dm['false_abstain']}/{dm['answerable_count']}"
        f" ({cm['false_abstain']}/{cm['answerable_count']} calibration)"
    )
    coverage = (
        f"{dm['answerable_coverage']:.6f} / "
        f"{cm['answerable_coverage']:.6f} calibration"
    )
    family_coverage = (
        f"{dm['family']['answerable_coverage']:.6f} / "
        f"{cm['family']['answerable_coverage']:.6f} calibration"
    )
    fingerprints = development_metadata["config"]
    return f"""# Phase 6B — Answerability calibration

Status: **{policy['status']}**

Status rationale: {policy['status_reason']}

## Policy contract

- Binary target: `answerable → ANSWER`; `unanswerable` and `ambiguous` → `ABSTAIN`.
- Deterministic safety reasons override any statistical candidate: `{', '.join(ABSTAIN_REASONS)}`.
- Fit and threshold selection: `development`; confirmation: `calibration`.
- Frozen test used: **NO**. Runtime gate changed: **NO**.
- BGE scores remain raw ranking signals, not probabilities.
- No post-hoc Platt or isotonic calibration was used; the logistic output is
  evaluated as a model probability, while single-feature scores remain raw.
- Unavailable across both exports and therefore excluded: `{', '.join(unavailable)}`.

## Selected candidate

- Method: `{selected['method']}`
- Features: `{selected_features}`
- Locked threshold: `{selected['threshold']:.12g}`
- Model serialization: `model.json` (portable coefficients/scaler when applicable)

| Metric | Result |
|---|---:|---:|
| False answers | {false_answers} |
| False-answer rate | {dm['false_answer_rate']:.6f} / {cm['false_answer_rate']:.6f} calibration |
| False abstentions | {false_abstentions} |
| Answerable coverage | {coverage} |
| AUROC | {dm.get('auroc')} / {cm.get('auroc')} calibration |
| AUPRC | {dm.get('auprc')} / {cm.get('auprc')} calibration |
| Family answerable coverage | {family_coverage} |

## Leakage and reproducibility

Excluded from model input: `{', '.join(LEAKAGE_FIELDS)}`.

Corpus fingerprint: `{fingerprints['corpus_fingerprint']}`  
Dataset fingerprint: `{fingerprints['dataset_fingerprint']}`  
Collection: `{fingerprints['collection']}`  
Reference candidate_k/top_n:
`{fingerprints['candidate_k']}/{fingerprints['top_n']}`

The policy artifact is evidence only. It is not wired into chat generation.

The selected operating point is deliberately safety-first. Its answerable
coverage is reported without an arbitrary acceptance threshold; the policy
remains **INCONCLUSIVE** when a critical slice has zero answerable coverage.
"""


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
