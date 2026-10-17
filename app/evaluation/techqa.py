"""RAGBench TechQA over the production RAG path: pure logic.

The frozen HOLDOUT50 questions are asked through the same search, evidence
and answer stream POST /chat uses. Each TechQA document is indexed as its own
Markdown file, so a question's relevant documents (from RAGBench's relevant
sentence keys) map to production source_ids. Semantic quality is graded by a
reviewer against the reference answer with the canonical rubric (CORRECT,
PARTIAL, INCORRECT, UNAVAILABLE); everything else here is deterministic.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.evaluation.mmlongbench import response_kind
from app.shared.slug import slugify

_SUPPORT_ID = re.compile(r"\[(E\d+\.S\d+)\]")
_DOC_INDEX = re.compile(r"^(\d+)")
SEMANTIC_LABELS = ("CORRECT", "PARTIAL", "INCORRECT", "UNAVAILABLE")


@dataclass(frozen=True)
class TechQAQuestion:
    qid: str
    row_idx: int
    question: str
    reference: str
    relevant_sources: tuple[str, ...]


def doc_file_name(text: str) -> str:
    """The Markdown file one TechQA document is indexed from, named by its
    content hash so the same document shared by several rows is one file."""
    return "techqa_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] + ".md"


def source_id_for_text(text: str) -> str:
    """The production source_id of that file (the filesystem connector keeps
    the extension in the slug)."""
    return slugify(doc_file_name(text), strip_extension=False)


def _relevant_sources(row: dict[str, Any]) -> tuple[str, ...]:
    documents = row.get("documents") or []
    sources: list[str] = []
    for key in row.get("all_relevant_sentence_keys") or []:
        match = _DOC_INDEX.match(str(key))
        if match is None or int(match.group(1)) >= len(documents):
            continue
        source = source_id_for_text(str(documents[int(match.group(1))]))
        if source not in sources:
            sources.append(source)
    return tuple(sources)


def holdout_questions(rows: list[dict[str, Any]], ids: list[str]) -> list[TechQAQuestion]:
    """The frozen questions in their frozen order. TechQA repeats some ids;
    the canonical rule keeps the lowest parquet row for each."""
    first: dict[str, int] = {}
    for index, row in enumerate(rows):
        first.setdefault(str(row["id"]), index)
    missing = [qid for qid in ids if qid not in first]
    if missing:
        raise ValueError(f"holdout ids not in the dataset: {missing}")
    return [
        TechQAQuestion(
            qid=qid,
            row_idx=first[qid],
            question=str(rows[first[qid]]["question"]),
            reference=str(rows[first[qid]].get("response") or ""),
            relevant_sources=_relevant_sources(rows[first[qid]]),
        )
        for qid in ids
    ]


def all_documents(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Every distinct document text by its file name."""
    return {
        doc_file_name(str(text)): str(text) for row in rows for text in row.get("documents") or []
    }


def cited_sources(answer: str, support_units: list[dict[str, Any]]) -> list[str]:
    """source_ids of the cited support units, in citation order; unknown ids
    are skipped."""
    by_id = {unit["support_id"]: unit for unit in support_units}
    sources: list[str] = []
    for support_id in _SUPPORT_ID.findall(answer):
        unit = by_id.get(support_id)
        if unit is not None and str(unit["source_id"]) not in sources:
            sources.append(str(unit["source_id"]))
    return sources


def _rate(values: Iterable[bool]) -> dict[str, Any]:
    values = list(values)
    if not values:
        return {"rate": None, "n": 0}
    return {"rate": round(sum(values) / len(values), 4), "n": len(values)}


def build_report(
    questions: list[TechQAQuestion],
    raws: list[dict[str, Any]],
    top_n: int,
    candidate_k: int,
    scores: dict[str, str] | None = None,
) -> dict[str, Any]:
    by_qid = {raw["qid"]: raw for raw in raws}
    pairs = [(q, by_qid[q.qid]) for q in questions]
    with_relevant = [(q, raw) for q, raw in pairs if q.relevant_sources]
    answered = [(q, raw) for q, raw in with_relevant if response_kind(raw) == "answered"]
    seconds = sorted(float(raw["seconds"]) for _, raw in pairs)
    semantic = None
    if scores is not None:
        counts = Counter(scores[q.qid] for q in questions)
        unknown = set(counts) - set(SEMANTIC_LABELS)
        if unknown:
            raise ValueError(f"unknown semantic labels: {sorted(unknown)}")
        total = len(questions)
        semantic = {
            "counts": dict(counts),
            "useful_rate": round((counts["CORRECT"] + counts["PARTIAL"]) / total, 4),
            "correct_rate": round(counts["CORRECT"] / total, 4),
            "incorrect_rate": round(counts["INCORRECT"] / total, 4),
            "unavailable_rate": round(counts["UNAVAILABLE"] / total, 4),
        }
    return {
        "questions": len(questions),
        "top_n": top_n,
        "candidate_k": candidate_k,
        "response_kinds": dict(Counter(response_kind(raw) for _, raw in pairs)),
        "retrieval_hit_top": _rate(
            bool(set(q.relevant_sources) & set(raw["top_sources"])) for q, raw in with_relevant
        ),
        "retrieval_hit_candidates": _rate(
            bool(set(q.relevant_sources) & set(raw["candidate_sources"]))
            for q, raw in with_relevant
        ),
        "citation_on_relevant": _rate(
            bool(set(q.relevant_sources) & set(raw["cited_sources"]))
            for q, raw in answered
            if raw["cited_sources"]
        ),
        "acl_leaks": sum(int(raw["acl_leaks"]) for _, raw in pairs),
        "median_seconds": seconds[len(seconds) // 2] if seconds else None,
        "semantic": semantic,
    }
