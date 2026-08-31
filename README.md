# Knowledge Base RAG

Production-style multilingual RAG platform with secure tenant boundaries,
hybrid retrieval, explicit evidence provenance, deterministic validation,
privacy-safe observability, and reproducible evaluation.

**Python** · **FastAPI** · **Qdrant** · **OpenAI / Ollama** · **React** ·
**OpenTelemetry** · **pytest**

Knowledge Base RAG is a local-first engineering portfolio system for
multilingual knowledge bases. It is designed around a practical question that
most RAG demos skip: what should happen when retrieved evidence, generated
claims, citations, and critical literals do not agree?

![RAG Operations Console Playground](docs/assets/rag-playground.jpg)

## Why This Project Exists

Retrieval quality alone does not make an answer trustworthy. A useful system
must preserve tenant boundaries, construct evidence deliberately, explain
which support units reached the model, validate the model's references, and
fail closed when a safety boundary cannot be established.

This project makes those boundaries explicit. It also treats evaluation as an
engineering control: a change is adopted only when it passes a decision rule
that was frozen before the result was known.

## What Makes It Different

The system goes beyond “upload a PDF, search vectors, call an LLM” with:

- dense and sparse retrieval fused with reciprocal rank fusion;
- server-owned tenant and role authorization before reranking or generation;
- SectionAware evidence construction with request-scoped support-unit IDs;
- deterministic validation of support identity and critical literal consistency;
- a frozen occurrence-ledger architecture for negation, corrections, signed
  values, versions, and repeated siblings;
- bounded OpenTelemetry/Jaeger signals plus controlled local forensic capture;
- an evaluation harness that separates retrieval, evidence, generation,
  validation, citation, and security failures.

## Engineering Highlights

| Engineering problem | System response |
| --- | --- |
| Cross-tenant retrieval | Server-owned ACL is enforced before reranking and generation. |
| Citation is not grounding | Request-scoped support IDs separate provenance from semantic correctness. |
| RAG failures are hard to diagnose | Retrieval → reranking → evidence → generation → validation → citation attribution. |
| Critical-value ambiguity | An immutable occurrence ledger keeps role decisions local to each occurrence. |
| Benchmark-driven tuning risk | Frozen datasets, hashes, preregistered gates, and preserved rejected experiments. |

## Key Results

The headline numbers below are from the canonical TechQA BGE-ON evaluation
record. They are benchmark results, not claims about live customer traffic or
general serving performance.

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Candidate evidence recall | **95.9%** | Required evidence was usually found in the candidate set. |
| Useful-answer rate | **70%** | Correct + Partial; this is not an accuracy claim. |
| Materially incorrect answers | **2%** | Wrong or materially misleading visible answers. |
| Unavailable / abstained | **28%** | The system did not provide a useful supported answer. |
| Strict fully-correct | **30%** | Separate full-completeness scoring, stricter than useful-answer rate. |

### Safety Evidence

Within the corrected TechQA evaluation, the support-ID and citation contracts
accepted no unknown, cross-query, hidden, or unauthorized support IDs, and had
zero citation contract failures:

| Safety check | Observed |
| --- | ---: |
| Unknown / cross-query / hidden / unauthorized support IDs accepted | **0** |
| Citation contract failures | **0** |

These are deterministic contract results from the evaluated corpus, not a
claim of formally proven system security.

Disabling BGE materially improved evidence completeness, but no robust
directional semantic advantage was distinguishable between the arms. Because
the preregistered semantic non-regression gate still failed, removal was not
authorized (`BGE_REMOVAL_NOT_SUPPORTED`). See the
[canonical evaluation report](artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/)
for the evidence and score definitions.

## Architecture

```mermaid
flowchart TD
    Query[Query] --> ACL[Tenant / ACL boundary]
    ACL --> Dense[Dense retrieval]
    ACL --> BM25[BM25 retrieval]
    Dense --> RRF[RRF fusion]
    BM25 --> RRF
    RRF --> Candidates["Authorized Top-20"]
    Candidates --> Rerank["BGE reranking"]
    Rerank --> Top5["Top-5"]
    Top5 --> Evidence[SectionAware Evidence Builder]
    Evidence --> Units[Support Units]
    Units --> LLM[LLM]
    LLM --> Answer["text + support_ids[]"]
    Answer --> Support[Support-ID validation]
    Support --> Critical[Architecture V2 critical-value validator]
    Critical --> Citation[Citation resolution]
    Citation --> Visible[Visible Answer]

    Critical -. bounded metadata .-> OTel[OTel / Jaeger]
    Critical -. controlled local details .-> Forensic[Forensic capture]
    RRF -. frozen measurements .-> Eval[Evaluation harness]
```

The runtime starts with an authenticated `UserContext` and server-owned tenant
ACL; unauthorized candidates never reach reranking or generation. FastAPI
owns authentication, authorization, retrieval, generation, SSE, and citation
resolution. Qdrant serves the active index. The React Operations Console
presents the resulting evidence and trace state; it is not an authorization
boundary.

## Failure Attribution

When an answer fails, the useful question is not only “was it wrong?” but “at
which boundary did it become wrong?” The runtime and evaluation records keep
these classes distinct:

```text
retrieval miss
  → reranker loss
  → evidence-packing loss
  → generation error
  → validator over-rejection
  → citation failure
```

The goal is to identify the first responsible system boundary, not merely to
assign a final pass/fail label. This makes it possible to improve the right
layer without hiding a retrieval limitation behind a validator metric or
calling a citation identity check semantic grounding.

## Architecture V2: Occurrence-Aware Validation

### Why the Validator Uses an Occurrence Ledger

Earlier validator prototypes added handling for negation, corrective claims,
signed values, versions, and same-value siblings. Repeated failures exposed a
structural problem: identity was lost between extraction, value matching,
masking, and text re-discovery. A value could be rejoined with the wrong role
or an inner unsigned value could be counted as an independent occurrence.

The old shape was:

```text
extract → value/type matching → text rediscovery → masking → re-extraction → validate
```

The frozen Architecture V2 shape is:

```text
one canonical extraction
  → immutable occurrence ledger
  → occurrence-local role classification
  → structured VALIDATE filter
  → frozen V3 value semantics
```

For example:

> The signed result is -204, not 204.

The conceptual ledger keeps identity attached to each occurrence:

```text
O1: -204  → VALIDATE
O2:  204  → SKIP_REJECTED_PREMISE
```

The `204` inside `-204` is not independently rediscovered. This is a small
example of the larger design principle: role decisions belong to occurrences,
not to globally normalized values.

Architecture V2 is frozen under
`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1` and is the default
validator in this portfolio runtime. Baseline and V3 remain explicit
server-side options for rollback and comparison. The implementation and
independent evidence are available in the
[Architecture V2 artifacts](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-implementation-v1/)
and [independent validation V2](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-independent-contract-validation-v2/).

## Safety Boundaries

The system deliberately separates three questions:

1. **Support identity and provenance:** support-ID validation proves that a
   cited support unit existed, was authorized, and was visible to the model.
2. **Critical literal consistency:** Architecture V2 checks deterministic
   consistency for values such as numbers, units, versions, dates, percentages,
   and identifiers.
3. **Semantic answer quality:** offline evaluation determines whether the
   answer actually fulfills the question from the evidence.

Support-ID validation does **not** prove semantic entailment. Critical-value
validation does **not** solve general semantic grounding. Keeping those claims
separate makes both the runtime behavior and the evaluation results easier to
reason about.

## Evaluation Philosophy

> A result changes the system only if it passes a decision rule frozen before
> the result is known.

| Experiment | What it taught us | Decision |
| --- | --- | --- |
| BGE removal | Disabling BGE materially improved evidence completeness, but the preregistered semantic non-regression gate still failed. | Keep BGE; `BGE_REMOVAL_NOT_SUPPORTED`. |
| Validator V1 | Improved metrics did not compensate for a locale-safety hard-gate failure. | Reject the candidate. |
| Validator V4/V5/V6 | Incremental polarity and masking fixes kept exposing occurrence-identity failures. | Stop patching; redesign the contract. |
| Architecture V2 | Fresh independent contract validation and runtime integration passed with identity and privacy gates intact. | Integrate the occurrence-ledger architecture. |

The rejected paths remain available as canonical evidence rather than being
rewritten into a success narrative. The historical V1 annotation defect and
its `FAILED` verdict are preserved; the later independent V2 validation is a
separate result.

## Runtime Status

Architecture V2 is the default validator in this portfolio runtime. The path
has been verified through a real local browser → API → RAG → validator →
telemetry flow, including direct Chrome CDP control, citation resolution, and
failure isolation.

This repository implements production-oriented controls, but it is a portfolio
system rather than a claim of operating a customer-facing production service.
There is no claim of live customer traffic, production SLOs, a completed
production canary, or a production promotion exercise. Architecture V2 shadow
is off by default.

## Features

### Retrieval

- Qwen3-Embedding-4B embeddings with the configured 1024-dimensional index.
- Qdrant dense and BM25 sparse retrieval with reciprocal rank fusion.
- BAAI/bge-reranker-v2-m3 over authorized candidates.
- SectionAware evidence packing under a bounded context budget.

### Grounding and Safety

- Mandatory tenant ACL and role boundaries before reranking or generation.
- Request-scoped support units and application-owned citation resolution.
- Frozen Architecture V2 occurrence ledger with fail-closed infrastructure
  handling.
- Untrusted context serialization and strict buffered validation mode.

### Evaluation

- Frozen populations, preregistration, hashes, scorecards, and decision records.
- Separate strict, useful, materially incorrect, and unavailable outcomes.
- Retrieval/evidence/generation/validator/citation failure attribution.
- Independent contract validation for safety-critical validator behavior.

### Observability

- OpenTelemetry traces with Jaeger inspection for chat and sync flows.
- Bounded architecture, outcome, role-count, duration, and error metadata.
- No raw query, answer, evidence, literal, prompt, or credential in normal
  telemetry.
- Controlled local forensic capture for occurrence-level diagnosis.

### Runtime

- FastAPI backend and React RAG Operations Console.
- Qdrant-backed index lifecycle with alias activation and rollback-aware sync.
- Server-side OpenAI/Ollama provider selection.
- SSE answer delivery with application-resolved citations.

## Quickstart

### Prerequisites

- Python 3.11+
- Docker Desktop or a compatible Docker Engine
- Node.js 22 and npm
- Native [Ollama](https://ollama.com) for local generation and embeddings

### Run locally

```bash
cp .env.example .env
ollama pull qwen3-embedding:4b
ollama pull qwen3.5:4b

docker compose up -d --build

cd frontend
npm ci
npm run dev
```

The copied environment enables the default evidence-backed support-unit path:
`RAG_PIPELINE_V2=true`, `SUPPORT_IDS_ENABLED=true`, and
`CRITICAL_VALIDATOR_VERSION=architecture_v2`. Open the frontend URL printed by
Vite, normally `http://localhost:5173`.
The compose backend normally serves on `http://localhost:8000`, Qdrant on
`6333`, and Jaeger on `16686`. A fresh installation must ingest documents
before retrieval can return evidence. An operator identity can trigger sync
from the console or the protected sync API.

For host-native backend development, run `docker compose up -d qdrant jaeger`,
then use `make dev` and run the frontend separately. The full environment
surface, including auth and CORS settings, is documented in
[`.env.example`](.env.example).

## Configuration

All validator selection is server-controlled. A query, header, cookie, body
field, or frontend preference cannot select a validator.

| Setting | Portfolio default | Purpose |
| --- | --- | --- |
| `RAG_PIPELINE_V2` | `true` | Default portfolio path for evidence-backed construction. |
| `SUPPORT_IDS_ENABLED` | `true` | Default support-unit output and application-owned support validation. |
| `CRITICAL_VALIDATOR_VERSION` | `architecture_v2` | `baseline`, `v3`, or `architecture_v2`. |
| `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED` | `false` | Diagnostic V2 shadow; off by default. |
| `CRITICAL_VALIDATOR_V3_SHADOW_ENABLED` | `false` | Optional diagnostic V3 shadow. |
| `GENERATION_PROVIDER` / model settings | Ollama / `qwen3.5:4b` | Local generation profile. |
| `RAG_FORENSIC_CAPTURE_ENABLED` | `false` | Controlled local metadata capture. |
| `RAG_FORENSIC_CAPTURE_RAW_TEXT` | `false` | Raw forensic text; never normal OTel. |

Invalid validator selectors fail closed. To compare or roll back explicitly,
set `CRITICAL_VALIDATOR_VERSION=baseline` or `v3`; no database, Qdrant,
reindexing, embedding, or document migration is required.

## Observability and Forensics

The normal trace contains bounded metadata such as validator version, outcome,
reason class, occurrence and role counts, duration, forced-abstain state, and
shadow status. It does not contain raw user content or per-occurrence IDs.
Normal telemetry stays bounded and content-free; deeper occurrence-level
diagnostics require explicit controlled local forensic capture.

When controlled local forensic capture is enabled, the artifact can expose the
occurrence ledger, role decisions, filtered `VALIDATE` IDs, and frozen V3
delegation result. This provides a debugging path without turning production
telemetry into a content store. Start with the
[Architecture V2 rollout note](docs/critical-validator-architecture-v2-rollout.md)
and the [local shadow-readiness evidence](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-shadow-readiness-v2/).

## Testing

The deterministic backend suite is the default verification path and does not
make provider calls:

```bash
pytest -m "not ollama_e2e"
ruff check app tests scripts
```

The latest frozen runtime checkpoint recorded **1245 passed, 1 skipped, and 6
deselected**. Counts may increase as reusable tests are added. Provider-backed
checks are explicit:

```bash
pytest -m "ollama_e2e"
```

Frontend checks are available when the UI changes:

```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

## Reproducible Evidence

The canonical artifact tree preserves preregistrations, frozen populations,
source hashes, scorecards, runtime reports, and decision records. It is
evidence for the engineering decisions, not a substitute for the concise
system description above.

Curated entry points:

- [Architecture V2 implementation](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-implementation-v1/)
- [Independent contract validation V1](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-independent-contract-validation-v1/)
- [Independent contract validation V2](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-independent-contract-validation-v2/)
- [Production integration review](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-production-integration-review-v1/)
- [Shadow readiness V2](artifacts/ragbench/canonical/critical-value-validator-architecture-v2-shadow-readiness-v2/)
- [Canonical RAGBench index](artifacts/ragbench/canonical/)

## Reviewer Fast Path

For a 10-minute technical review:

1. Start with the diagram and [Architecture V2: Occurrence-Aware Validation](#architecture-v2-occurrence-aware-validation).
2. Review the [system architecture](docs/architecture.md) and [security boundary](docs/security.md).
3. Inspect the [Architecture V2 adapter](app/evaluation/critical_validator_architecture_v2.py), [occurrence ledger](app/evaluation/critical_occurrences.py), and [role classifier](app/evaluation/critical_roles.py).
4. Read the reusable [integration contract tests](tests/test_critical_validator_architecture_v2_integration.py).
5. Read one [canonical TechQA report](artifacts/ragbench/canonical/techqa-reranker-corrected-holdout-execution-v2/).
6. Run the local UI, inspect a trace in Jaeger, and compare the concise [rollout note](docs/critical-validator-architecture-v2-rollout.md) with the preserved canonical evidence.

## Limitations

- Strict full-completeness remains below the useful-answer rate.
- Conservative abstention is a deliberate safety trade-off, not a solved
  answerability problem.
- BGE reranking is measured as expensive for latency-sensitive serving; the
  removal gate did not pass, so the model remains enabled.
- The deterministic validator does not establish arbitrary semantic
  entailment.
- T4 boolean normalization and T6 unit-equivalence remain separate unresolved
  mechanism classes; they were not folded into Architecture V2 activation.
- The current benchmark corpus is short for distinguishing larger token-aware
  chunk boundaries.
- Local/demo authentication is not a complete customer-production identity
  design.
- This project makes no claim of real customer production traffic, production
  SLOs, a live canary, or a production promotion.

## Roadmap

- SectionAware multi-section invariant audit.
- Better failure-attribution dashboards.
- BGE serving, microbatching, or adaptive reranking experiments.
- Broader benchmark corpora with longer documents and more multilingual cases.
- Evaluator/final-evidence alignment work for semantic completeness.

## Deeper Documentation

- [System architecture](docs/architecture.md)
- [Security model](docs/security.md)
- [Reranking decision](docs/reranking.md)
- [Chunking decision](docs/chunking.md)
- [Evaluation corpus design](docs/evaluation-dataset.md)
- [Architecture decisions](docs/adr/README.md)
- [Engineering history](docs/PLANNING.md)

## License

See the repository license and notices for distribution terms.
