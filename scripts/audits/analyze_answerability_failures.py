"""Static failure analysis for Phase 6B answerability features.

Only existing authorized top-five exports are read. Structural features are
derived locally from scores/source IDs; no retrieval, generation, or frozen
test is run.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.evaluation.answerability import extract_structural_features
from scripts.calibration.calibrate_answerability import (
    ABSTAIN_REASONS,
    _apply_safety_override,
    _finite_thresholds,
    evaluate_predictions,
    target,
)

ROOT = Path(__file__).resolve().parents[2]
FEATURE_DIR = ROOT / "artifacts/phase-6/answerability-features"
OUTPUT_DIR = ROOT / "artifacts/phase-6/failure-analysis"
MODEL_PATH = ROOT / "artifacts/phase-6/calibration/model.json"

BASE_FEATURES = (
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
STRUCTURAL_FEATURES = tuple(
    extract_structural_features(
        [1.0, 0.8, 0.6, 0.4, 0.2],
        ["source-a", "source-a", "source-b", "source-c", "source-c"],
    )
    .as_dict()
    .keys()
)
ANALYSIS_FEATURES = BASE_FEATURES + STRUCTURAL_FEATURES
CRITICAL_CATEGORIES = (
    "standard_answerable",
    "hard_answerable",
    "cross_lingual",
    "multi_document",
    "injection_bearing",
    "version_conflict",
)
FINAL_DIAGNOSIS = "RETRIEVAL_FEATURES_INSUFFICIENT"


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _enrich(records: list[dict]) -> list[dict]:
    enriched = []
    for record in records:
        features = dict(record["features"])
        structural = extract_structural_features(
            [float(value) for value in record["top_raw_reranker_scores"]],
            record["top_authorized_source_ids"],
        )
        features.update(structural.as_dict())
        enriched.append({**record, "features": features})
    return enriched


def _model_predictions(records: list[dict]) -> np.ndarray:
    model_data = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    order = model_data["feature_order"]
    x = np.array([[record["features"][name] for name in order] for record in records])
    scale = np.array(model_data["scaler_scale"], dtype=float)
    scale[scale == 0] = 1.0
    linear = (
        (x - np.array(model_data["scaler_mean"], dtype=float)) / scale
    ) @ np.array(model_data["coefficients"], dtype=float)
    linear += float(model_data["intercept"])
    probabilities = 1.0 / (1.0 + np.exp(-np.clip(linear, -700, 700)))
    return _apply_safety_override(
        records,
        (probabilities >= float(model_data["threshold"])).astype(int),
    )


def _required_sources(record: dict) -> set[str]:
    return set(record.get("required_source_ids") or record.get("expected_source_ids") or [])


def _gold_presence(record: dict) -> dict[str, bool]:
    required = _required_sources(record)
    retrieved = set(record.get("top_authorized_source_ids", []))
    return {
        "any_required_present": bool(required & retrieved),
        "all_required_present": bool(required) and required <= retrieved,
    }


def _taxonomy_row(record: dict, prediction: int) -> dict[str, Any]:
    presence = _gold_presence(record)
    answerable = record["answerability_label"] == "answerable"
    predicted_answer = prediction == 0
    cause = "other"
    if answerable and prediction == 1:
        if record["deterministic_reason"] in ABSTAIN_REASONS:
            cause = "deterministic_safety_abstain"
        elif (
            len(_required_sources(record)) > 1
            and presence["any_required_present"]
            and not presence["all_required_present"]
        ):
            cause = "multi_document_partial_evidence"
        elif not presence["all_required_present"]:
            cause = "retrieval_failure"
        else:
            cause = "gate_failure_with_gold_present"
    elif answerable and predicted_answer and not presence["all_required_present"]:
        cause = "unsafe_answer_candidate"
    return {
        "query_id": record["query_id"],
        "case_family": record["case_family"],
        "category": record["category"],
        "tenant": record["tenant"],
        "query_language": record["query_language"],
        "evidence_language": record["evidence_language"],
        "language_pair": record["language_pair"],
        "answerability_label": record["answerability_label"],
        "required_source_ids": sorted(_required_sources(record)),
        "top_authorized_source_ids": record["top_authorized_source_ids"],
        "deterministic_reason": record["deterministic_reason"],
        "predicted_outcome": "ANSWER" if predicted_answer else "ABSTAIN",
        **presence,
        "cause": cause,
    }


def _taxonomy(records: list[dict], predictions: np.ndarray) -> dict[str, Any]:
    rows = [
        _taxonomy_row(record, int(prediction))
        for record, prediction in zip(records, predictions)
    ]
    answerable = [
        row
        for row in rows
        if row["answerability_label"] == "answerable"
    ]
    answerable_failures = [
        row
        for row in answerable
        if row["predicted_outcome"] == "ABSTAIN"
    ]
    causes = (
        "retrieval_failure",
        "gate_failure_with_gold_present",
        "multi_document_partial_evidence",
        "deterministic_safety_abstain",
        "other",
    )
    return {
        "total_records": len(rows),
        "answerable_count": len(answerable),
        "rows": rows,
        "answerable_failure_counts": {
            cause: sum(row["cause"] == cause for row in answerable_failures)
            for cause in causes
        },
        "unsafe_answer_with_gold_absent": sum(
            row["predicted_outcome"] == "ANSWER"
            and not row["all_required_present"]
            for row in rows
        ),
    }


def _failure_summary(rows: list[dict]) -> dict[str, Any]:
    answerable = [
        row for row in rows if row["answerability_label"] == "answerable"
    ]
    deterministic = [
        row for row in rows if row["deterministic_reason"] in ABSTAIN_REASONS
    ]
    eligible = [
        row for row in rows if row["deterministic_reason"] not in ABSTAIN_REASONS
    ]
    gold_present = [row for row in answerable if row["all_required_present"]]
    return {
        "total_records": len(rows),
        "answerable_count": len(answerable),
        "deterministic_abstain_count": len(deterministic),
        "statistical_gate_eligible_count": len(eligible),
        "false_abstain_count": sum(
            row["predicted_outcome"] == "ABSTAIN" for row in answerable
        ),
        "false_abstain_given_gold_present": sum(
            row["predicted_outcome"] == "ABSTAIN" for row in gold_present
        ),
        "gold_present_answerable_count": len(gold_present),
        "gold_present_answerable_coverage": (
            sum(row["predicted_outcome"] == "ANSWER" for row in gold_present)
            / len(gold_present)
            if gold_present
            else 0.0
        ),
        "answer_when_gold_absent": sum(
            row["predicted_outcome"] == "ANSWER"
            and not row["all_required_present"]
            for row in rows
        ),
    }


def _critical_slices(rows: list[dict]) -> dict[str, dict[str, Any]]:
    output = {}
    for category in sorted({row["category"] for row in rows}):
        all_selected = [row for row in rows if row["category"] == category]
        selected = [
            row
            for row in all_selected
            if row["answerability_label"] == "answerable"
        ]
        gold_present = [row for row in selected if row["all_required_present"]]
        output[category] = {
            "n": len(all_selected),
            "answerable_count": len(selected),
            "gold_all_required_top5_present": len(gold_present),
            "predicted_answer": sum(
                row["predicted_outcome"] == "ANSWER" for row in all_selected
            ),
            "false_abstain_with_gold_present": sum(
                row["predicted_outcome"] == "ABSTAIN" for row in gold_present
            ),
            "retrieval_failure": sum(
                row["cause"] == "retrieval_failure" for row in selected
            ),
            "multi_document_partial_evidence": sum(
                row["cause"] == "multi_document_partial_evidence"
                for row in selected
            ),
            "coverage": (
                sum(row["predicted_outcome"] == "ANSWER" for row in selected)
                / len(selected)
                if selected
                else 0.0
            ),
        }
    return output


def _summary(values: list[float]) -> dict[str, float | int | None]:
    keys = (
        "n",
        "mean",
        "median",
        "std",
        "min",
        "p10",
        "p25",
        "p75",
        "p90",
        "p95",
        "max",
    )
    if not values:
        return {key: None for key in keys}
    array = np.array(values, dtype=float)
    return {
        "n": len(values),
        "mean": round(float(array.mean()), 6),
        "median": round(float(np.median(array)), 6),
        "std": round(float(array.std()), 6),
        "min": round(float(array.min()), 6),
        "p10": round(float(np.percentile(array, 10)), 6),
        "p25": round(float(np.percentile(array, 25)), 6),
        "p75": round(float(np.percentile(array, 75)), 6),
        "p90": round(float(np.percentile(array, 90)), 6),
        "p95": round(float(np.percentile(array, 95)), 6),
        "max": round(float(array.max()), 6),
    }


def _ks_statistic(first: list[float], second: list[float]) -> float | None:
    if not first or not second:
        return None
    values = sorted(set(first + second))
    statistic = max(
        abs(
            sum(value <= point for value in first) / len(first)
            - sum(value <= point for value in second) / len(second)
        )
        for point in values
    )
    return round(float(statistic), 6)


def _feature_shift(development: list[dict], calibration: list[dict]) -> dict:
    output = {}
    for label, predicate in (
        ("ANSWER", lambda record: target(record) == 0),
        ("ABSTAIN", lambda record: target(record) == 1),
    ):
        output[label] = {}
        for feature in ANALYSIS_FEATURES:
            dev_values = [
                float(record["features"][feature])
                for record in development
                if predicate(record) and record["features"].get(feature) is not None
            ]
            cal_values = [
                float(record["features"][feature])
                for record in calibration
                if predicate(record) and record["features"].get(feature) is not None
            ]
            dev_stats = _summary(dev_values)
            cal_stats = _summary(cal_values)
            pooled = math.sqrt(
                (float(np.std(dev_values)) ** 2 + float(np.std(cal_values)) ** 2)
                / 2
            )
            output[label][feature] = {
                "development": dev_stats,
                "calibration": cal_stats,
                "median_shift": (
                    round(
                        float(cal_stats["median"] - dev_stats["median"]),
                        6,
                    )
                    if dev_stats["median"] is not None
                    and cal_stats["median"] is not None
                    else None
                ),
                "standardized_shift": (
                    round(
                        (float(cal_stats["mean"]) - float(dev_stats["mean"]))
                        / pooled,
                        6,
                    )
                    if pooled > 1e-12
                    else 0.0
                ),
                "ks_statistic": _ks_statistic(dev_values, cal_values),
            }
    return output


def _slice_distributions(records: list[dict]) -> dict:
    output = {}
    for category in CRITICAL_CATEGORIES:
        selected = [
            record
            for record in records
            if record["category"] == category
            and record["answerability_label"] == "answerable"
        ]
        output[category] = {
            feature: _summary(
                [
                    float(record["features"][feature])
                    for record in selected
                    if record["features"].get(feature) is not None
                ]
            )
            for feature in ANALYSIS_FEATURES
        }
    return output


def _stability(development: list[dict], calibration: list[dict]) -> list[dict]:
    y_dev = np.array([target(record) for record in development])
    y_cal = np.array([target(record) for record in calibration])
    rows = []
    for feature in ANALYSIS_FEATURES:
        dev = np.array(
            [record["features"].get(feature) for record in development],
            dtype=float,
        )
        cal = np.array(
            [record["features"].get(feature) for record in calibration],
            dtype=float,
        )
        if not np.isfinite(dev).all() or not np.isfinite(cal).all():
            continue
        if len(set(y_dev)) < 2 or len(set(y_cal)) < 2:
            continue
        raw_dev = roc_auc_score(y_dev, dev)
        reverse_dev = roc_auc_score(y_dev, -dev)
        direction = -1 if reverse_dev > raw_dev else 1
        dev_scores = dev * direction
        cal_scores = cal * direction
        dev_auc = roc_auc_score(y_dev, dev_scores)
        cal_auc = roc_auc_score(y_cal, cal_scores)
        dev_ap = average_precision_score(y_dev, dev_scores)
        cal_ap = average_precision_score(y_cal, cal_scores)
        rows.append(
            {
                "feature": feature,
                "direction": (
                    "higher_is_abstain"
                    if direction == 1
                    else "lower_is_abstain"
                ),
                "dev_auroc": round(float(dev_auc), 6),
                "cal_auroc": round(float(cal_auc), 6),
                "auroc_delta": round(float(cal_auc - dev_auc), 6),
                "dev_auprc": round(float(dev_ap), 6),
                "cal_auprc": round(float(cal_ap), 6),
                "auprc_delta": round(float(cal_ap - dev_ap), 6),
                "stable": abs(float(cal_auc - dev_auc)) <= 0.1,
            }
        )
    return sorted(rows, key=lambda row: (-row["cal_auroc"], row["feature"]))


def _correlations(records: list[dict]) -> list[dict]:
    matrix = np.array(
        [
            [record["features"].get(feature) for feature in ANALYSIS_FEATURES]
            for record in records
        ],
        dtype=float,
    )
    rows = []
    for left_index, left in enumerate(ANALYSIS_FEATURES):
        for right_index in range(left_index + 1, len(ANALYSIS_FEATURES)):
            value = float(np.corrcoef(matrix[:, left_index], matrix[:, right_index])[0, 1])
            if math.isfinite(value) and abs(value) >= 0.9:
                rows.append(
                    {
                        "feature_a": left,
                        "feature_b": ANALYSIS_FEATURES[right_index],
                        "correlation": round(value, 6),
                    }
                )
    return rows


def _available(
    features: list[str], development: list[dict], calibration: list[dict]
) -> list[str]:
    return [
        feature
        for feature in features
        if all(
            record["features"].get(feature) is not None
            for record in development + calibration
        )
    ]


def _fit_candidate(
    development: list[dict], calibration: list[dict], features: list[str]
) -> dict:
    model = Pipeline(
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
    x_dev = np.array(
        [[record["features"][feature] for feature in features] for record in development]
    )
    y_dev = np.array([target(record) for record in development])
    model.fit(x_dev, y_dev)
    dev_probabilities = model.predict_proba(x_dev)[:, 1]
    candidates = []
    for threshold in _finite_thresholds(dev_probabilities):
        predictions = _apply_safety_override(
            development,
            (dev_probabilities >= threshold).astype(int),
        )
        metrics = evaluate_predictions(
            development,
            predictions,
            dev_probabilities,
            dev_probabilities,
        )
        candidates.append({"threshold": threshold, "development": metrics})
    selected = max(
        candidates,
        key=lambda candidate: (
            candidate["development"]["balanced_accuracy"],
            candidate["development"]["answerable_coverage"],
            -candidate["development"]["false_answer"],
            -candidate["threshold"],
        ),
    )
    threshold = selected["threshold"]
    x_cal = np.array(
        [
            [record["features"][feature] for feature in features]
            for record in calibration
        ]
    )
    cal_probabilities = model.predict_proba(x_cal)[:, 1]
    cal_predictions = _apply_safety_override(
        calibration,
        (cal_probabilities >= threshold).astype(int),
    )
    return {
        "features": features,
        "threshold": round(float(threshold), 12),
        "development": evaluate_predictions(
            development,
            _apply_safety_override(
                development,
                (dev_probabilities >= threshold).astype(int),
            ),
            dev_probabilities,
            dev_probabilities,
        ),
        "calibration": evaluate_predictions(
            calibration,
            cal_predictions,
            cal_probabilities,
            cal_probabilities,
        ),
        "development_threshold_curve": [
            {
                "threshold": round(float(candidate["threshold"]), 12),
                "false_answer_rate": candidate["development"][
                    "false_answer_rate"
                ],
                "answerable_coverage": candidate["development"][
                    "answerable_coverage"
                ],
            }
            for candidate in candidates
        ],
    }


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _metadata() -> dict:
    summary = json.loads(
        (FEATURE_DIR / "calibration-summary.json").read_text(encoding="utf-8")
    )
    config = summary["config"]
    return {
        "git_sha": _git_sha(),
        "corpus_fingerprint": config["corpus_fingerprint"],
        "dataset_fingerprint": config["dataset_fingerprint"],
        "collection": config["collection"],
        "candidate_k": config["candidate_k"],
        "top_n": config["top_n"],
        "frozen_test_used": False,
        "generation_invoked": False,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _report(
    metadata: dict,
    development: dict,
    calibration: dict,
    development_summary: dict,
    calibration_summary: dict,
    stability: list[dict],
    candidates: dict,
) -> str:
    stable = [row["feature"] for row in stability if row["stable"]][:8]
    unstable = [row["feature"] for row in stability if not row["stable"]][:8]
    lines = [
        "# Phase 6B.1 — Answerability failure analysis",
        "",
        "Static analysis of existing authorized top-five exports. Runtime behavior, "
        "retrieval configuration, and final-policy.json were not changed.",
        "",
        "## Failure taxonomy",
        "",
        "| Split | Answerable | Retrieval failure | Gate failure with gold | "
        "Multi-document partial | Deterministic |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in (("Development", development), ("Calibration", calibration)):
        counts = result["answerable_failure_counts"]
        lines.append(
            f"| {name} | {result['answerable_count']} | "
            f"{counts['retrieval_failure']} | "
            f"{counts['gate_failure_with_gold_present']} | "
            f"{counts['multi_document_partial_evidence']} | "
            f"{counts['deterministic_safety_abstain']} |"
        )
    lines.extend(
        [
            "",
            "Development gold-present coverage: "
            f"{development_summary['gold_present_answerable_coverage']:.6f}.",
            "Calibration gold-present coverage: "
            f"{calibration_summary['gold_present_answerable_coverage']:.6f}.",
            "Unsafe ANSWER with gold absent: "
            f"{development_summary['answer_when_gold_absent']} development, "
            f"{calibration_summary['answer_when_gold_absent']} calibration.",
            "",
            "## Feature stability",
            "",
            "Most stable: " + (", ".join(stable) or "none") + ".",
            "Most unstable: " + (", ".join(unstable) or "none") + ".",
            "",
            "## Redesigned candidates",
            "",
        ]
    )
    for name, result in candidates["candidates"].items():
        dev = result["development"]
        cal = result["calibration"]
        lines.append(
            f"- {name}: development coverage {dev['answerable_coverage']:.6f}, "
            f"calibration coverage {cal['answerable_coverage']:.6f}, "
            f"calibration false answers {cal['false_answer']}/{cal['true_abstain']}."
        )
    lines.extend(
        [
            "",
            "No redesigned candidate is recommended yet. Critical-slice coverage "
            "and cross-split stability require another development iteration.",
            f"Final diagnosis: {FINAL_DIAGNOSIS}.",
            "",
            f"Corpus fingerprint: {metadata['corpus_fingerprint']}",
            f"Dataset fingerprint: {metadata['dataset_fingerprint']}",
            "Frozen test used: NO; generation invoked: NO.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    development = _enrich(_load(FEATURE_DIR / "development.jsonl"))
    calibration = _enrich(_load(FEATURE_DIR / "calibration.jsonl"))
    development_families = {record["case_family"] for record in development}
    calibration_families = {record["case_family"] for record in calibration}
    if development_families & calibration_families:
        raise ValueError("development/calibration case-family leakage")

    metadata = _metadata()
    development_predictions = _model_predictions(development)
    calibration_predictions = _model_predictions(calibration)
    development_taxonomy = _taxonomy(development, development_predictions)
    calibration_taxonomy = _taxonomy(calibration, calibration_predictions)
    development_rows = development_taxonomy["rows"]
    calibration_rows = calibration_taxonomy["rows"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(
        OUTPUT_DIR / "failure-taxonomy.json",
        {
            "metadata": metadata,
            "diagnosis": {
                "status": FINAL_DIAGNOSIS,
                "reason": (
                    "Most false abstentions have gold evidence present, but "
                    "redesigned retrieval-derived features do not generalize "
                    "with an acceptable false-answer trade-off."
                ),
            },
            "development": development_taxonomy,
            "calibration": calibration_taxonomy,
        },
    )
    _write_json(
        OUTPUT_DIR / "false-abstention-cases.json",
        {
            "metadata": metadata,
            "development": [
                row
                for row in development_rows
                if row["answerability_label"] == "answerable"
                and row["predicted_outcome"] == "ABSTAIN"
            ],
            "calibration": [
                row
                for row in calibration_rows
                if row["answerability_label"] == "answerable"
                and row["predicted_outcome"] == "ABSTAIN"
            ],
        },
    )
    _write_json(
        OUTPUT_DIR / "critical-slice-root-causes.json",
        {
            "metadata": metadata,
            "development": _critical_slices(development_rows),
            "calibration": _critical_slices(calibration_rows),
        },
    )
    _write_json(
        OUTPUT_DIR / "feature-shift.json",
        {
            "metadata": metadata,
            "development_vs_calibration": _feature_shift(development, calibration),
            "development_answerable_by_category": _slice_distributions(development),
            "calibration_answerable_by_category": _slice_distributions(calibration),
        },
    )
    stability = _stability(development, calibration)
    _write_csv(stability, OUTPUT_DIR / "feature-stability.csv")
    _write_csv(
        _correlations(development + calibration),
        OUTPUT_DIR / "feature-correlations.csv",
    )
    _write_json(
        OUTPUT_DIR / "redesigned-feature-distributions.json",
        {
            "metadata": metadata,
            "development": _slice_distributions(development),
            "calibration": _slice_distributions(calibration),
        },
    )

    candidate_sets = {
        "current_compact": BASE_FEATURES,
        "source_level_compact": (
            "top1_score",
            "top1_top2_margin",
            "mean_top3_score",
            "source_top1_score",
            "source_top2_score",
            "source_margin",
            "source_mean_score",
            "source_count",
            "source_rank_entropy",
            "source_score_entropy",
            "top_source_chunk_share",
        ),
        "relative_structural_compact": (
            "score_decay_1_2",
            "score_decay_1_3",
            "score_decay_1_5",
            "top1_to_mean_top5_ratio",
            "top1_to_median_top5_ratio",
            "top2_to_mean_top5_ratio",
            "score_range_top5",
            "score_iqr_top5",
            "unique_source_ratio_top5",
            "duplicate_source_ratio_top5",
            "source_rank_entropy",
            "source_score_entropy",
        ),
        "hybrid_compact": (
            "top1_score",
            "top1_top2_margin",
            "mean_top3_score",
            "mean_top5_score",
            "score_decay_1_2",
            "score_decay_1_3",
            "unique_source_ratio_top5",
            "top_source_chunk_share",
            "source_margin",
            "source_score_entropy",
        ),
    }
    candidate_results = {
        "metadata": metadata,
        "diagnosis": FINAL_DIAGNOSIS,
        "selection": (
            "development balanced-accuracy operating point for comparison only"
        ),
        "candidates": {},
    }
    for name, requested in candidate_sets.items():
        features = _available(list(requested), development, calibration)
        candidate_results["candidates"][name] = _fit_candidate(
            development,
            calibration,
            features,
        )
    _write_json(
        OUTPUT_DIR / "redesigned-candidate-results.json",
        candidate_results,
    )

    development_summary = _failure_summary(development_rows)
    calibration_summary = _failure_summary(calibration_rows)
    _write_json(
        OUTPUT_DIR / "revised-metrics.json",
        {
            "metadata": metadata,
            "development": development_summary,
            "calibration": calibration_summary,
            "statistical_only": {
                "development": evaluate_predictions(
                    development,
                    development_predictions,
                ),
                "calibration": evaluate_predictions(
                    calibration,
                    calibration_predictions,
                ),
            },
        },
    )
    (OUTPUT_DIR / "report.md").write_text(
        _report(
            metadata,
            development_taxonomy,
            calibration_taxonomy,
            development_summary,
            calibration_summary,
            stability,
            candidate_results,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
