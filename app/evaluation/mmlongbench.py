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
import difflib
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

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
        # MMLongBench-Doc-V2 also writes "Not answerable or 0 or none".
        return not str(self.answer).startswith(NOT_ANSWERABLE)


def _literal_list(value: str | None) -> list[Any]:
    if not value:
        return []
    parsed = ast.literal_eval(value)
    return list(parsed) if isinstance(parsed, list | tuple) else [parsed]


# Evidence a text chunker can reach; a question whose evidence is only a chart
# or a figure needs visual evidence, not better chunks.
TEXTUAL_SOURCES = frozenset({"Pure-text (Plain-text)", "Table", "Generalized-text (Layout)"})


def select_focused_rows(
    table: list[dict[str, Any]], doc_ids: list[str], *, unanswerable_per_doc: int
) -> list[int]:
    """Rows of the given documents whose evidence includes text, a table or
    layout text, plus the first ``unanswerable_per_doc`` unanswerable
    questions of each document (refusal stays measured without dominating),
    in row order."""
    selected, refusals = [], Counter[str]()
    wanted = set(doc_ids)
    for index, row in enumerate(table):
        doc = row["doc_id"]
        if doc not in wanted:
            continue
        if row["answer"] == NOT_ANSWERABLE:
            if refusals[doc] < unanswerable_per_doc:
                refusals[doc] += 1
                selected.append(index)
            continue
        if set(_literal_list(row.get("evidence_sources"))) & TEXTUAL_SOURCES:
            selected.append(index)
    return selected


def parse_question(row: dict[str, Any], row_idx: int) -> PilotQuestion:
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


# MMLongBench-Doc-V2 (github.com/VectifyAI/MMLongBench-Doc-V2) corrects gold
# answers and rewrites ambiguous questions in V1's row order, dropping rows
# whose document cannot be read. Its samples carry no V1 row index.
SAME_QUESTION_MIN_RATIO = 0.5


def _same_question(v1: dict[str, Any], v2: dict[str, Any]) -> bool:
    """The same question when it shares the document and its text, its answer
    or its evidence pages (a rewritten question keeps the answer, a corrected
    answer keeps the text)."""
    if v1["doc_id"] != v2["doc_id"]:
        return False
    ratio = difflib.SequenceMatcher(None, v1["question"], v2["question"]).ratio()
    return (
        ratio >= SAME_QUESTION_MIN_RATIO
        or str(v1["answer"]).strip() == str(v2["answer"]).strip()
        or v1["evidence_pages"] == v2["evidence_pages"]
    )


def corrected_rows(
    v1: list[dict[str, Any]], v2: list[dict[str, Any]]
) -> list[dict[str, Any] | None]:
    """Each V1 row's V2 sample, None for a row V2 dropped. Rows are aligned in
    order; a V2 file that does not align with every one of its samples is
    refused rather than half applied."""
    rows: list[dict[str, Any] | None] = []
    j = 0
    for row in v1:
        if j < len(v2) and _same_question(row, v2[j]):
            rows.append({**row, **v2[j]})
            j += 1
        else:
            rows.append(None)
    if j != len(v2):
        raise ValueError(f"V2 samples do not align with V1 rows: {j} of {len(v2)} matched")
    return rows


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
_NUMBER_OR_WORD = re.compile(r"(?:(?<!\w)-)?\d+(?:\.\d+)?|\b(?:" + "|".join(_NUMBER_WORDS) + r")\b")
# Golds below this are found on almost any page ("2", "12%"), so seeing one
# in the page text says nothing about whether the answer is there.
SMALL_NUMBER_GOLD = 100
# A long gold item one slip away from the prediction is the gold's typo
# ("Unioon Bank of India").
TYPO_MIN_CHARS = 10
TYPO_MIN_RATIO = 0.92
_SUPPORT_ID = re.compile(r"\[(E\d+\.S\d+)\]")
_MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
# The day of a written date ("January 28, 2023", "24th of March") is not a
# number the answer states.
_DATE_DAY = re.compile(
    rf"\b{_MONTH_NAME}\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_NAME}",
    re.IGNORECASE,
)
# A verified calculation as the answer renders it: "(calculation: 10 / 24 * 100 = 41.7%)".
# The expression may hold parentheses ("10 / (10 + 14) * 100"); it holds no "=".
_CALCULATION_RESULT = re.compile(r"\(calculation: [^=]*=\s*([^()=]+)\)")
# A verified count as the answer renders it: "(count: 13 listed items)".
_COUNT_RESULT = re.compile(r"\(count: (\d+) listed items\)")


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


def _close(value: float, gold: float) -> bool:
    return abs(value - gold) <= max(abs(gold) * 0.01, 1e-6)


def _numeric_match(prediction: str, gold: float) -> bool:
    return any(_close(value, gold) for value in _numbers(prediction))


def _is_year(value: float) -> bool:
    return value.is_integer() and 1900 <= value <= 2100


def _stated_number(prediction: str, gold: float) -> float | None:
    """The first number the answer states, in text order (number words
    included). A year is skipped unless the gold is one, so "In 2013, 41%..."
    states 41; so is the day of a written date ("January 28, 2023")."""
    cleaned = _DATE_DAY.sub(" ", re.sub(r"(?<=\d),(?=\d{3})", "", prediction.lower()))
    for match in _NUMBER_OR_WORD.finditer(cleaned):
        token = match.group()
        value = float(_NUMBER_WORDS[token]) if token in _NUMBER_WORDS else float(token)
        if _is_year(value) and not _is_year(gold):
            continue
        return value
    return None


def _typo_match(prediction: str, gold: str) -> bool:
    if len(gold) < TYPO_MIN_CHARS:
        return False
    words, size = prediction.split(), len(gold.split())
    return any(
        SequenceMatcher(None, " ".join(words[start : start + size]), gold).ratio() >= TYPO_MIN_RATIO
        for start in range(max(1, len(words) - size + 1))
    )


def _item_matches(prediction: str, gold: str) -> bool:
    gold_numbers = _numbers(gold)
    bare = _normalize(gold).replace("%", "").replace(" ", "").replace(".", "")
    if gold_numbers and bare.isdigit():
        return _numeric_match(prediction, gold_numbers[0])
    gold_text, text = _normalize(gold), _normalize(prediction)
    return gold_text in text or _typo_match(text, gold_text)


# A number the answer writes with a unit that scales it: "25.04%" is the ratio
# 0.2504, "1,358 (000's)" is 1,358,000.
_SCALED = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(%|percent\b|\(000['’]?s\)|thousands?\b|millions?\b|billions?\b)",
    re.IGNORECASE,
)
_FACTORS = {"%": 0.01, "percent": 0.01, "thousand": 1e3, "million": 1e6, "billion": 1e9}


def _factor(unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("("):
        return 1e3
    return _FACTORS.get(unit, _FACTORS.get(unit.removesuffix("s"), 1.0))


def _value_matches(prediction: str, value: float, gold_text: str, gold: float) -> bool:
    """The value, or the value as its unit scales it where the answer writes
    one next to it. A gold that is itself a percentage is not read as a ratio."""
    if _close(value, gold):
        return True
    for number, unit in _SCALED.findall(prediction):
        factor = _factor(unit)
        if factor == 0.01 and "%" in gold_text:
            continue
        if float(number.replace(",", "")) == value and _close(value * factor, gold):
            return True
    return False


def answer_matches(prediction: str, gold: str, answer_format: str) -> bool:
    if gold == NOT_ANSWERABLE or answer_format == "None":
        return False
    # Support-id citations ("[E1.S2]") carry digits that are not part of the answer.
    prediction = _SUPPORT_ID.sub(" ", prediction)
    if answer_format in ("Int", "Float"):
        gold_numbers = _numbers(gold)
        if not gold_numbers:
            return False
        # A computed answer states its operands first; its value is the
        # verified calculation's result (a decrease may be negative).
        calculation = _CALCULATION_RESULT.search(prediction) or _COUNT_RESULT.search(prediction)
        if calculation:
            results = _numbers(calculation.group(1))
            return bool(results) and _value_matches(
                prediction, abs(results[0]), gold, gold_numbers[0]
            )
        stated = _stated_number(prediction, gold_numbers[0])
        return stated is not None and _value_matches(prediction, stated, gold, gold_numbers[0])
    if answer_format == "List":
        try:
            items = [str(item) for item in _literal_list(gold)]
        except (ValueError, SyntaxError):
            items = [gold]
        return bool(items) and all(_item_matches(prediction, item) for item in items)
    return _item_matches(prediction, gold)


def _small_number_gold(question: PilotQuestion) -> bool:
    if question.answer_format in ("Int", "Float"):
        values = _numbers(question.answer)
    elif question.answer_format == "List":
        try:
            items = [str(item) for item in _literal_list(question.answer)]
        except (ValueError, SyntaxError):
            return False
        if not all(_normalize(item).replace("%", "").replace(".", "").isdigit() for item in items):
            return False
        values = [value for item in items for value in _numbers(item)]
    else:
        return False
    return bool(values) and all(abs(value) < SMALL_NUMBER_GOLD for value in values)


def gold_visible(question: PilotQuestion, texts: Iterable[str]) -> bool | None:
    """Whether the gold answer appears in the given text (the same lenient
    match answers are scored with). A lower bound: an answer the question
    asks to compute (a difference, a count) is not in any text.

    A numeric gold is looked for among all of the text's numbers, exactly:
    answer scoring reads only the first number an answer states, and its 1%
    tolerance would find a near number on any page full of figures."""
    if not question.answerable or _small_number_gold(question):
        return None
    text = "\n".join(texts)
    if question.answer_format in ("Int", "Float"):
        gold = _numbers(question.answer)
        return bool(gold) and gold[0] in _numbers(text)
    return answer_matches(text, question.answer, question.answer_format)


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
    # Whether the gold answer appears in the text of the evidence pages, and
    # in the evidence the model was given; None when not measured.
    gold_in_page_text: bool | None = None
    gold_in_evidence: bool | None = None
    # "retrieved", or "gold_page" when the model was given the evidence
    # pages instead of what retrieval found.
    evidence: str = "retrieved"
    # Whether an evidence page is among the pages of the support units the
    # model was shown; None for results saved before this was recorded.
    evidence_page_seen: bool | None = None

    @property
    def loss_stage(self) -> str | None:
        """The first stage that lost the gold answer, for a wrong answer to
        an answerable question: not in the evidence pages' text (a parsing
        loss, or an answer that has to be computed), not retrieved, retrieved
        but not in what the model saw, or seen and still not answered."""
        if not self.question.answerable or self.correct:
            return None
        if self.ingested is False or self.gold_in_page_text is False:
            return "not_in_page_text"
        if self.evidence == "retrieved" and self.retrieved_top_k is False:
            return "retrieval"
        if self.evidence_page_seen is False:
            return "assembly"
        if self.gold_in_page_text is None or self.gold_in_evidence is None:
            # A small-number gold (or an old result) cannot be located in
            # text, so the loss cannot be pinned on assembly or generation.
            return "unmeasured"
        if self.gold_in_evidence is False:
            return "assembly"
        return "generation"

    @property
    def kind(self) -> str:
        if self.response_kind is not None:
            return self.response_kind
        return "answered" if self.answered else "model_abstained"


# A refusal is only credited when the system chose it: the model abstained,
# or the validator blocked an unsupported answer. An output that failed to
# parse is a failure, even when the user sees a refusal.
REFUSAL_KINDS = ("model_abstained", "validator_blocked")


def response_kind(result: dict[str, Any]) -> str:
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


def _rate(values: Iterable[bool | None]) -> dict[str, Any]:
    applicable = [value for value in values if value is not None]
    if not applicable:
        return {"rate": None, "n": 0}
    return {"rate": round(sum(applicable) / len(applicable), 4), "n": len(applicable)}


def _stage_metrics(outcomes: list[QuestionOutcome], top_k: int, candidate_k: int) -> dict[str, Any]:
    answerable = [o for o in outcomes if o.question.answerable]
    return {
        "questions": len(outcomes),
        "ingestion_evidence_page_coverage": _rate(o.ingested for o in answerable),
        f"retrieval_hit_at_{top_k}": _rate(o.retrieved_top_k for o in answerable),
        f"retrieval_hit_at_{candidate_k}": _rate(o.retrieved_candidates for o in answerable),
        "gold_in_page_text": _rate(o.gold_in_page_text for o in answerable),
        "gold_in_evidence": _rate(o.gold_in_evidence for o in answerable),
        "evidence_page_seen": _rate(o.evidence_page_seen for o in answerable),
        "answer_accuracy": _rate(o.correct for o in answerable),
        "citation_accuracy": _rate(o.citation_on_evidence for o in answerable),
    }


def build_report(
    outcomes: list[QuestionOutcome], *, top_k: int, candidate_k: int
) -> dict[str, Any]:
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
        "loss_stages": dict(
            sorted(Counter(o.loss_stage for o in answerable if o.loss_stage).items())
        ),
        "acl_leaks": sum(o.acl_leaks for o in outcomes),
    }


def _pages(values: Iterable[Any] | None) -> list[tuple[str, int]]:
    return [(str(source_id), int(page)) for source_id, page in values or []]


def outcome_from_result(
    question: PilotQuestion, result: dict[str, Any], *, source_id: str
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
        gold_in_page_text=result.get("gold_in_page_text"),
        gold_in_evidence=result.get("gold_in_evidence"),
        evidence=result.get("evidence") or "retrieved",
        evidence_page_seen=(
            page_hit(_pages(result["seen_pages"]), source_id, pages)
            if result.get("seen_pages") is not None and pages
            else None
        ),
    )


# "page 3", or a section path ending in "(page 8)" / "(pages 5–6)".
_PAGE_LABEL = re.compile(r"(?:^|\()pages? (\d+)(?:\s*[–-]\s*(\d+))?\)?$")


def payload_pages(payload: dict[str, Any]) -> list[int]:
    """Every page a chunk covers: page_number through page_end."""
    first = int(payload["page_number"])
    last = int(payload.get("page_end") or first)
    return list(range(first, max(first, last) + 1))


def cited_pages(answer: str, support_units: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """(source_id, page) of every page a cited support unit covers, in
    citation order: the unit's page fields, or else its section label's
    "page N" / "(pages N–M)". Units without a page (Markdown sections) and
    unknown ids are skipped."""
    by_id = {unit["support_id"]: unit for unit in support_units}
    pages: list[tuple[str, int]] = []
    for support_id in _SUPPORT_ID.findall(answer):
        unit = by_id.get(support_id)
        if unit is None:
            continue
        for number in _unit_pages(unit):
            page = (str(unit["source_id"]), number)
            if page not in pages:
                pages.append(page)
    return pages


def _unit_pages(unit: dict[str, Any]) -> list[int]:
    if unit.get("page_number") is not None:
        first = int(unit["page_number"])
        last = int(unit.get("page_end") or first)
        return list(range(first, max(first, last) + 1))
    match = _PAGE_LABEL.search(str(unit.get("section_label") or ""))
    if match is None:
        return []
    first = int(match.group(1))
    last = int(match.group(2) or first)
    return list(range(first, max(first, last) + 1))
