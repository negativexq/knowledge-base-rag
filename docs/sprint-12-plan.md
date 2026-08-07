# Sprint 12 Plan — Safety and Correctness

## Goal

Close two real correctness/safety gaps an external code review found, and
add CI (this project's first). Verified both findings against current
code before planning anything — neither had drifted since the review.

## Finding 1: `grounded=True` with zero citations (confirmed, `app/llm/grounding.py:45`)

```python
return GroundingResult(
    grounded=len(ungrounded_citations) == 0,
    ...
)
```

`ungrounded_citations` is `[c for c in citations_found if c not in valid_locations]`
— when `citations_found` is empty (no `[s.…]` tag anywhere in the answer),
`ungrounded_citations` is also empty, so `grounded` computes to `True`.
Confirmed by reading the code, not just the review's quote, and by an
existing test that encodes this exact behavior as *intentional*:
`tests/test_grounding.py::test_grounding_with_no_citations_at_all_is_considered_grounded`.

**Real impact of the old behavior**: any answer that makes a factual
claim but includes zero citations — the most dangerous hallucination
shape, since there's no citation tag at all for a reader to even
side-eye — was reported `grounded: True` in the UI (a reassuring green
✅) and in the `generate.grounded` trace attribute. This is strictly
worse than a fabricated citation (which the existing checks already
catch): a citation-free hallucination gave a *false positive* trust
signal instead of a warning.

The one legitimate case that produces zero citations by design is the
`NOT_FOUND_PHRASE` reply ("I could not find this in the document.") —
it makes no factual claim, so there's nothing to warn about either. The
old code conflated "vacuously fine, nothing to check" with "actively
verified, trust this" — both rendered as the same `grounded=True`,
indistinguishable to a reader or to any code branching on the field.

### Fix

Split the single boolean into what it's actually made of:

```python
@dataclass(frozen=True)
class GroundingResult:
    has_citations: bool
    citations_valid: bool
    grounded: bool  # has_citations and citations_valid
    citations_found: list[tuple[str, str, str]]
    ungrounded_citations: list[tuple[str, str, str]]
```

`grounded` stays as a field (not removed) — every existing caller
(`app/llm/generate.py`'s SSE `grounding` event, its `generate.grounded`
span attribute, and the UI) reads `.grounded`/`grounding_event["grounded"]`
and needs no restructuring. `has_citations`/`citations_valid` are the new,
finer-grained signal a caller that *cares about the distinction* (the UI,
after this sprint) can branch on instead of collapsing "nothing to check"
and "checked and failed" into the same `False`.

**Caller audit** (grep for `check_grounding`/`GroundingResult`/`.grounded`/
`grounded=` across `app/` and `tests/`, every hit inspected):
- `app/llm/generate.py` — reads `.grounded`, `.citations_found`,
  `.ungrounded_citations` only. Unaffected by the new fields; behavior
  changes only because the *value* of `.grounded` is now correct for the
  zero-citation case.
- `app/ui/pages/chat.py` — same three fields via the SSE event dict. This
  is the one real behavior-visible spot: previously a zero-citation
  answer showed "✅ Grounded"; after the fix, `grounded` is `False` for
  that case too, and the existing binary UI (✅ grounded / ⚠️ warning with
  `ungrounded_citations`) would show an empty-list warning
  (`"...retrieved context: []"`) for a `NOT_FOUND_PHRASE` reply — a
  confusing message for a reply that made no claim at all. Fixed by
  giving the UI a third state, keyed on the new `has_citations` field:
  no citations → neutral caption (nothing to verify), citations but
  invalid → the existing warning, all valid → the existing ✅.
- All other hits are test files — assertions on `.grounded is True/False`
  in scenarios that always have real, either-valid-or-fabricated
  citations (never the empty case) — unaffected. The one exception is
  `test_grounding_with_no_citations_at_all_is_considered_grounded` itself,
  which encoded the bug as a spec; its assertion flips.

### README: naming the mechanism honestly

The task that started this sprint calls this out directly: what
`check_grounding` does is **citation integrity validation** — it proves
every citation tag in the answer points to a real chunk that was actually
in the retrieved context, from the claimed source. It does **not** prove
**semantic grounding** — that the specific factual claim next to a
citation is actually *supported by* that chunk's text. A model could cite
a real, correctly-attributed chunk right next to a claim that chunk
doesn't actually support, and this check would report `grounded: True`.
README gets this distinction spelled out explicitly, plus a "future work"
note: claim-level semantic support checking (e.g., an NLI/entailment
check between each claim and its cited chunk's text) is a real
improvement this system doesn't attempt yet.

## Finding 2: `ensure_collection()` silently deletes on schema mismatch (confirmed, `app/ingestion/qdrant_store.py:20-27`)

```python
def ensure_collection(self) -> None:
    if self._client.collection_exists(self._collection_name):
        info = self._client.get_collection(self._collection_name)
        if SPARSE_VECTOR_NAME in (info.config.params.sparse_vectors or {}):
            return
        self._client.delete_collection(self._collection_name)  # <-- destructive
    self._client.create_collection(...)
```

The comment above the delete call ("Safe here because dev collections are
re-ingestable") is the actual bug: it's an assumption about *who's
calling this*, not something the function can verify. `ensure_collection()`
runs on every `ingest_path`/`ingest_connector` call — any real deployment
pointed at the wrong `QDRANT_COLLECTION_NAME`, or a collection that
predates the sparse-vector schema and holds real production data, gets
silently and irreversibly deleted the next time a sync runs. No confirmation,
no error, no log line distinguishing "recreated an empty dev collection"
from "destroyed a collection with real data."

### Fix

Fail fast instead: if a collection exists and doesn't have the expected
sparse vector, raise a clear exception naming the collection and what's
wrong, and touch nothing. Recreating a genuinely-empty/dev collection
becomes an explicit, human-initiated action (delete it yourself, or point
at a fresh collection name) rather than something `ensure_collection()`
decides on your behalf.

```python
class UnexpectedCollectionSchemaError(Exception):
    """Raised when an existing Qdrant collection doesn't have the sparse
    vector this app requires, instead of silently deleting it — see
    docs/sprint-12-plan.md."""
```

## CI: this project's first — production-rag-platform has none

Checked `production-rag-platform/.github/workflows/` — doesn't exist.
No prior-art to port; designed from scratch for this project's actual
constraints:

- **`lint`**: `ruff check app tests` — fast, no services needed.
- **`test`**: a real Qdrant service container (`qdrant/qdrant:v1.12.4`,
  matching `docker-compose.yml`'s pin) via GitHub Actions' native
  `services:` support — cheap and reliable to run for real in CI, and the
  whole test suite already skip-guards on a live port check
  (`_port_open("localhost", 6333)`), so nothing new needs to be taught
  about CI; the Qdrant-only tests (`test_filters_e2e.py`) now actually run
  instead of skipping. **No Ollama in CI** — deliberately: it needs a
  real native binary plus multi-GB model pulls, which is slow, flaky
  (network-dependent), and not what GitHub-hosted runners are for; every
  Ollama-gated test already skips cleanly when port 11434 isn't
  reachable, so CI just gets a smaller, real subset rather than a fully
  mocked one — no test needs modification for this to work correctly.
- **`docker-build`**: `docker build .` only — no `docker run`. A run-based
  smoke test would eagerly load the cross-encoder/sparse-encoder models
  from HuggingFace at import time (`app/wiring.py::build_chat_dependencies`),
  a real network dependency that would make CI flaky for a check that
  isn't this job's actual purpose. `docker build` alone still catches the
  regression class this job exists for: a broken `Dockerfile`, a
  `requirements.txt` resolution failure (including a CUDA/torch wheel
  creeping back in — Sprint 11's fix), or a missing `COPY`.

Triggers: `push` to `main` and `pull_request` — standard, no scheduled
runs (nothing here needs a nightly check).
