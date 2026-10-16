"""MMLongBench-Doc pilot: pinned-manifest downloads, question parsing,
deterministic answer scoring and a stage-by-stage report sliced by evidence
type.

The benchmark's documents are third-party PDFs with no license stated on
the dataset card, so they never enter the repository: a manifest pins the
dataset revision and every file's size and git blob id, the files land in
the gitignored data/ folder, and only question row ids and results are
committed under artifacts/.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

NOT_ANSWERABLE = "Not answerable"

# Evidence-source labels as the dataset writes them, mapped to short slice
# names used in reports.
EVIDENCE_TYPES = {
    "Pure-text (Plain-text)": "text",
    "Generalized-text (Layout)": "layout",
    "Table": "table",
    "Chart": "chart",
    "Figure": "figure",
}
SLICES = ("text", "layout", "table", "chart", "figure")


class ChecksumMismatchError(Exception):
    pass


@dataclass(frozen=True)
class ManifestFile:
    """A file pinned by size plus content hash: the git blob id for files
    the Hub stores in git, or the sha256 for LFS files (whose tree entry's
    git id belongs to the LFS pointer, not the content)."""

    path: str
    size: int
    git_oid: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Manifest:
    dataset: str
    revision: str
    files: tuple[ManifestFile, ...]
    question_rows: tuple[int, ...]

    def url_for(self, file: ManifestFile) -> str:
        return f"https://huggingface.co/datasets/{self.dataset}/resolve/{self.revision}/{file.path}"


def load_manifest(path: str | Path) -> Manifest:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Manifest(
        dataset=raw["dataset"],
        revision=raw["revision"],
        files=tuple(
            ManifestFile(
                path=f["path"],
                size=int(f["size"]),
                git_oid=f.get("git_oid"),
                sha256=f.get("sha256"),
            )
            for f in raw["files"]
        ),
        question_rows=tuple(int(row) for row in raw["question_rows"]),
    )


def git_blob_oid(data: bytes) -> str:
    """The id git (and the HuggingFace Hub tree API) gives a file's
    content: sha1 over a "blob <size>\\0" header plus the bytes. Lets a
    download be checked against the Hub's own listing locally."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _matches(data: bytes, file: ManifestFile) -> bool:
    if len(data) != file.size:
        return False
    if file.sha256 is not None:
        return hashlib.sha256(data).hexdigest() == file.sha256
    return file.git_oid is not None and git_blob_oid(data) == file.git_oid


def download_manifest_files(
    manifest: Manifest, dest: str | Path, fetch: Callable[[str], bytes]
) -> list[Path]:
    """Fetch every manifest file into dest, keeping the manifest's relative
    paths. A file already present and matching is not fetched again; a
    fetched file is verified before it is written, so a mismatch leaves
    nothing behind."""
    dest = Path(dest)
    paths = []
    for file in manifest.files:
        target = dest / file.path
        if target.is_file() and _matches(target.read_bytes(), file):
            paths.append(target)
            continue
        data = fetch(manifest.url_for(file))
        if not _matches(data, file):
            expected = f"sha256 {file.sha256}" if file.sha256 else f"git oid {file.git_oid}"
            raise ChecksumMismatchError(
                f"{file.path}: expected {file.size} bytes with {expected}, got {len(data)} bytes "
                f"(sha256 {hashlib.sha256(data).hexdigest()}, git oid {git_blob_oid(data)})"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        paths.append(target)
    return paths


@dataclass(frozen=True)
class PilotQuestion:
    row_idx: int
    doc_id: str
    doc_type: str
    question: str
    answer: str
    answer_format: str
    evidence_pages: tuple[int, ...]
    evidence_types: tuple[str, ...]

    @property
    def answerable(self) -> bool:
        return self.answer != NOT_ANSWERABLE


def _literal_list(value: str | None) -> list:
    if not value:
        return []
    parsed = ast.literal_eval(value)
    return list(parsed) if isinstance(parsed, list | tuple) else [parsed]


def parse_question(row: dict, row_idx: int) -> PilotQuestion:
    return PilotQuestion(
        row_idx=row_idx,
        doc_id=row["doc_id"],
        doc_type=row["doc_type"],
        question=row["question"],
        answer=row["answer"],
        answer_format=row["answer_format"],
        evidence_pages=tuple(int(page) for page in _literal_list(row["evidence_pages"])),
        evidence_types=tuple(
            EVIDENCE_TYPES[source] for source in _literal_list(row["evidence_sources"])
        ),
    )


# --- answer scoring -------------------------------------------------------
#
# Deterministic and lenient on purpose: a local 4B model answers in full
# sentences, while the dataset's gold answers are short. A Str answer counts
# when the normalized gold text appears in the normalized answer; a number
# counts when any number in the answer is within 1% of it; a list counts
# when every item does. This is a "contains" score, not the benchmark's
# official LLM-extracted score.

_NUMBER_WORDS = {
    word: index
    for index, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
# A minus sign counts only when it does not join two tokens, so a range like
# "1981-1982" reads as two positive years.
_NUMBER = re.compile(r"(?:(?<!\w)-)?\d+(?:\.\d+)?")
_SUPPORT_ID = re.compile(r"\[(E\d+\.S\d+)\]")


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^\w%.' -]+", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return " ".join(text.split())


def _numbers(text: str) -> list[float]:
    cleaned = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    values = [float(match) for match in _NUMBER.findall(cleaned)]
    words = re.findall(r"[a-z]+", cleaned)
    values += [float(_NUMBER_WORDS[word]) for word in words if word in _NUMBER_WORDS]
    return values


def _numeric_match(prediction: str, gold: float) -> bool:
    tolerance = max(abs(gold) * 0.01, 1e-6)
    return any(abs(value - gold) <= tolerance for value in _numbers(prediction))


def _item_matches(prediction: str, gold: str) -> bool:
    gold_numbers = _numbers(gold)
    bare = _normalize(gold).replace("%", "").replace(" ", "").replace(".", "")
    if gold_numbers and bare.isdigit():
        return _numeric_match(prediction, gold_numbers[0])
    return _normalize(gold) in _normalize(prediction)


def answer_matches(prediction: str, gold: str, answer_format: str) -> bool:
    if gold == NOT_ANSWERABLE or answer_format == "None":
        return False
    # Support-id citations ("[E1.S2]") carry digits that are not part of the answer.
    prediction = _SUPPORT_ID.sub(" ", prediction)
    if answer_format in ("Int", "Float"):
        gold_numbers = _numbers(gold)
        return bool(gold_numbers) and _numeric_match(prediction, gold_numbers[0])
    if answer_format == "List":
        try:
            items = [str(item) for item in _literal_list(gold)]
        except (ValueError, SyntaxError):
            items = [gold]
        return bool(items) and all(_item_matches(prediction, item) for item in items)
    return _item_matches(prediction, gold)


def page_hit(
    results: Iterable[tuple[str, int]], source_id: str, evidence_pages: tuple[int, ...]
) -> bool:
    pages = set(evidence_pages)
    return any(sid == source_id and page in pages for sid, page in results)


# --- report ---------------------------------------------------------------


@dataclass(frozen=True)
class QuestionOutcome:
    """One question's result at every stage. None means the stage does not
    apply (an unanswerable question has no evidence page to find)."""

    question: PilotQuestion
    ingested: bool | None
    retrieved_top_k: bool | None
    retrieved_candidates: bool | None
    answered: bool
    correct: bool | None
    citation_on_evidence: bool | None
    acl_leaks: int
    # How the response ended (see response_kind); None derives it from
    # `answered` for callers that only know that much.
    response_kind: str | None = None

    @property
    def kind(self) -> str:
        if self.response_kind is not None:
            return self.response_kind
        return "answered" if self.answered else "model_abstained"


# A refusal is only credited when the system chose it: the model abstained,
# or the validator blocked an unsupported answer. An output that failed to
# parse is a failure, even when the user sees a refusal.
REFUSAL_KINDS = ("model_abstained", "validator_blocked")


def response_kind(result: dict) -> str:
    """How a response ended, from its validation event fields."""
    abstain = result.get("abstain")
    codes = result.get("validator_failure_codes")
    if abstain is None and codes is None:
        return "no_verdict"
    if not abstain:
        return "answered"
    codes = codes or []
    if any(code.endswith("_INVALID") for code in codes):
        return "output_invalid"
    if codes:
        return "validator_blocked"
    return "model_abstained"


def _rate(values: Iterable[bool | None]) -> dict:
    applicable = [value for value in values if value is not None]
    if not applicable:
        return {"rate": None, "n": 0}
    return {"rate": round(sum(applicable) / len(applicable), 4), "n": len(applicable)}


def _stage_metrics(outcomes: list[QuestionOutcome], top_k: int, candidate_k: int) -> dict:
    answerable = [o for o in outcomes if o.question.answerable]
    return {
        "questions": len(outcomes),
        "ingestion_evidence_page_coverage": _rate(o.ingested for o in answerable),
        f"retrieval_hit_at_{top_k}": _rate(o.retrieved_top_k for o in answerable),
        f"retrieval_hit_at_{candidate_k}": _rate(o.retrieved_candidates for o in answerable),
        "answer_accuracy": _rate(o.correct for o in answerable),
        "citation_accuracy": _rate(o.citation_on_evidence for o in answerable),
    }


def build_report(outcomes: list[QuestionOutcome], *, top_k: int, candidate_k: int) -> dict:
    answerable = [o for o in outcomes if o.question.answerable]
    unanswerable = [o for o in outcomes if not o.question.answerable]
    return {
        "overall": _stage_metrics(outcomes, top_k, candidate_k),
        "slices": {
            name: _stage_metrics(
                [o for o in outcomes if name in o.question.evidence_types], top_k, candidate_k
            )
            for name in SLICES
        },
        "answerability": {
            "unanswerable_correctly_refused": _rate(o.kind in REFUSAL_KINDS for o in unanswerable),
            "answerable_coverage": _rate(o.answered for o in answerable),
        },
        "response_kinds": dict(sorted(Counter(o.kind for o in outcomes).items())),
        "acl_leaks": sum(o.acl_leaks for o in outcomes),
    }


def _pages(values: Iterable) -> list[tuple[str, int]]:
    return [(str(source_id), int(page)) for source_id, page in values or []]


def outcome_from_result(
    question: PilotQuestion, result: dict, *, source_id: str
) -> QuestionOutcome:
    """Score one saved result (a results.jsonl row), so a report can be
    rebuilt without asking the model again."""
    kind = response_kind(result)
    answer = str(result.get("answer") or "")
    answered = kind == "answered" and bool(answer.strip())
    if not question.answerable:
        return QuestionOutcome(
            question=question,
            ingested=None,
            retrieved_top_k=None,
            retrieved_candidates=None,
            answered=answered,
            correct=None,
            citation_on_evidence=None,
            acl_leaks=int(result.get("acl_leaks") or 0),
            response_kind=kind,
        )
    chars = {int(page): count for page, count in (result.get("evidence_page_chars") or {}).items()}
    pages = question.evidence_pages
    return QuestionOutcome(
        question=question,
        ingested=all(chars.get(page, 0) > 0 for page in pages) if pages else None,
        retrieved_top_k=page_hit(_pages(result.get("top_pages")), source_id, pages),
        retrieved_candidates=page_hit(_pages(result.get("candidate_pages")), source_id, pages),
        answered=answered,
        correct=answered and answer_matches(answer, question.answer, question.answer_format),
        citation_on_evidence=(
            page_hit(_pages(result.get("cited_pages")), source_id, pages) if answered else None
        ),
        acl_leaks=int(result.get("acl_leaks") or 0),
        response_kind=kind,
    )


_PAGE_LABEL = re.compile(r"^page (\d+)$")


def cited_pages(answer: str, support_units: list[dict]) -> list[tuple[str, int]]:
    """(source_id, page) of every support unit the answer cites, in citation
    order, read from the unit's "page N" section label. Units without a page
    (Markdown sections) and unknown ids are skipped."""
    by_id = {unit["support_id"]: unit for unit in support_units}
    pages: list[tuple[str, int]] = []
    for support_id in _SUPPORT_ID.findall(answer):
        unit = by_id.get(support_id)
        match = _PAGE_LABEL.match(str((unit or {}).get("section_label") or ""))
        if unit is None or match is None:
            continue
        page = (str(unit["source_id"]), int(match.group(1)))
        if page not in pages:
            pages.append(page)
    return pages
