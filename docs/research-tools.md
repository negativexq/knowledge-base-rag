# Agent research tools

The PydanticAI research agent has eleven function tools. Availability depends on
request dependencies, feature flags, provider capabilities and the remaining
request budget. No new graph framework, parser dependency or external service is
required. The default production scope verifier remains mandatory.

| Tool | Contract |
| --- | --- |
| `search` | Hybrid retrieval with optional document/version anchor, physical page and seen-point exclusion; or bounded literal terms/phrase search with section and offset. |
| `find_documents` | Find permitted document anchors by indexed source name, optional title or headings, and exact indexed content version. |
| `read_document_section` | Reopen an evidence block already admitted to the ledger. |
| `navigate_document` | Read an indexed outline, section, page, neighboring chunks or literal matches. |
| `list_document_elements` | Enumerate detected ruled tables, embedded images, caption candidates and bookmarks on a physical PDF page. |
| `inspect_table` | Read extracted headers/cells and surrounding page text from an immutable PDF; admit the complete returned batch before exposing it. |
| `inspect_region` | Read a selected detected region or explicit physical PDF page with a separate visual verification call. |
| `compare_evidence` | Align 2–10 existing authorized support units and their source/version metadata without a model call. |
| `calculate` | Existing deterministic arithmetic and operand checks. |
| `resolve_calculation` | Existing evidence-bound operand planning and computation. |
| `read_pages` | Existing verified reading of top/named pages. |

## Search and discovery

Production chat and the MMLongBench runner share `ResearchRetriever`, built from
server-owned context and request source scope. The agent supplies only narrowing
filters, never tenant IDs or permission grants. A support anchor fixes source
**type**, source ID and document content version. Hybrid filtering is performed
before retrieval/reranking; scoped tool queries return raw reranked chunks so
section expansion cannot reintroduce excluded points or widen a page filter.
The application also checks returned document/page scope before ledger admission.
The original one-argument retrieval callback is retained for legacy callers;
unsupported scoped hybrid queries receive a recoverable tool error rather than
silently dropping their filters.

`terms` searches for all case-insensitive substrings; `phrase` matches a
whitespace-normalized case-insensitive literal sequence. They use the indexed
text directly, without an embedding or LLM call. Discovery matches indexed name,
title (when present) and headings, not inferred release names or dates. The
current connector/index schema does not provide a universal document-date or
product-release field. A content hash must not be interpreted as a release number.

Literal search and discovery scan at most 2,000 authorized indexed points.
They report `scan_limited`; absence in a partial scan never establishes absence
from the corpus. Literal search returns up to 20 whole passages/60,000 characters;
discovery returns up to 10 document anchors. Follow `next_offset` when present.
No metadata-only anchor bypasses the evidence ledger: if its evidence cannot be
admitted, it is not returned as a usable document reference.

Search admission distinguishes `duplicate_blocks`, `empty_blocks` and
`budget_excluded_blocks`, with `remaining_evidence_tokens`. Append-only support
IDs retain their original meaning. Excluded evidence is never returned as raw
text through another tool. Old runs lacking these counters cannot reliably be
classified as duplicate-only searches.

## PDF structure and visual inspection

PDF tools require a current authorized filesystem support anchor and a renderer
supporting version-checked snapshots. The indexed SHA-256 must match the exact
bytes read; snapshots remain request-local, with a 64 MiB source-file limit.
Every call checks the current ledger authorization even when a snapshot is cached.
Ingestion, structural inspection and page rendering share a process-wide reentrant
lock because PyMuPDF table extraction uses shared global state. CPU work remains
off the event loop; this serializes PDF work within a worker, not across workers.
No arbitrary file path, URL, shell, Python expression or model-selected rectangle
is accepted. Region IDs are reconstructed from the pinned source by the server.

Structural extraction uses the existing PyMuPDF table parser. Tables retain raw
cleaned cell rows, headers, physical page and bounding box. `inspect_table`
returns at most 50 data rows per batch; complete rows and surrounding text enter
the ledger with their own stable support IDs. It reports pagination and limited
context. Oversized/unextractable tables should be read visually. Header inference,
merged cells, units and footnotes can still be wrong or incomplete; extracted
structure does not replace semantic validation. No re-ingestion is required for
these tools because structure is read from the matching source snapshot on demand.

The element list is deliberately **not a complete semantic figure inventory**.
Embedded images may be logos; vector figures and unruled tables may be missed.
Caption candidates and bookmarks are navigation hints, not citable answer facts.
Enumeration is paginated per page, up to physical page 2,000. Visual counts need
actual page inspection and sufficient coverage.

For an element, `inspect_region` shows its crop with nearby context and the full
page to both the reader and the separate checker. For an explicit physical page,
it shows the full page. Both calls share the request budget. A reading is returned
only when the independent check accepts both what is shown and question scope.
The agent must select its server-owned `visual_reading_id`; it cannot relabel the
reading as text evidence. This remains a probabilistic visual check, not a proof.

`compare_evidence` exposes exact authorized passages and provenance differences.
It does not infer semantic contradictions, adjudicate an authoritative version,
or permit the agent to skip final deterministic/scope/release validation.

## Budget and observability

When scope validation is enabled, orchestration reserves one model request and
`min(8000, max_tokens / 4)` estimated tokens for it. Before the last available
research response, tools are hidden. Tools with nested model calls are hidden
unless their calls, a subsequent research response and scope verification fit the
request limit. Nested providers also enforce the response/verification reserve.

Local token preflight counts serialized research history and tool schemas plus
output allowance; nested visual estimates include an image allowance. This is an
estimate across tokenizers/providers, not an exact spending ceiling. Actual
provider usage remains authoritative and PydanticAI's shared limits still apply.
The verifier also has a token preflight; oversized candidates fail closed. The
existing total timeout still applies; no separate wall-clock reserve is promised.

New tools use the same content-free `tool.*` spans and SSE progress events as
existing tools. PDF/resolver nested model requests remain nested `llm.request`
spans. Search admission counts and input/reserve estimates are allowlisted trace
attributes; no page text, cell values, images or prompts are added to span
attributes. Research activity has labels for every new tool. Forensic capture
retains the existing opt-in content policy.

## Validation

Offline tests use real generated PDFs, in-memory Qdrant and PydanticAI FunctionModel
loops. They cover literal/hybrid filters, discovery, source/version boundaries,
live grants/revocation, cell/context extraction, oversized evidence exclusion,
source-version mismatch, separate visual checking, cached snapshot revocation,
content-free spans, comparisons and final verification request reservation.
Live benchmark results belong in a separately recorded artifact; passing these
integration checks alone does not establish an accuracy improvement.
