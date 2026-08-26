# Evaluation Corpus v2

Evaluation Corpus v2 is a preparation artifact for the next retrieval and
answerability benchmark. It expands the old four-document/small-fixture setup
without changing production documents, the active Qdrant alias, or any
production configuration. The previous 220-question set remains available at
`tests/fixtures/embedding_benchmark_golden_v2.json` for historical benchmark
reproducibility.

## Corpus design

The corpus lives under `data/evaluation/evaluation-corpus-v2/` and contains 20
fictional Northstar Cloud documents: 15 Markdown files and five generated,
text-selectable PDFs. It covers Turkish and English content, two tenants,
short and long documents, heading-heavy and paragraph-heavy Markdown,
bullet/table-like policy text, repeated terminology, regional rules,
versioned policies, cross-document references, and controlled adversarial
document text.

The long-document set includes `long-policy-tr.md`,
`employee-handbook-en.md`, `support-playbook.md`, and five 15-page PDF
fixtures. The generated PDF sources are deterministic and do not require OCR.
The manifest records each source identity, tenant, language, content type, and
path. Question labels are stored separately and are never inserted into the
corpus documents.

## Golden dataset schema

`golden-dataset-v2.json` uses stable IDs and explicit evaluator-owned fields:

- `question`, `query_language`, `evidence_language`, and `language_pair`
- `category`, `tags`, `difficulty`, and `rationale`
- `answerability`: `answerable`, `unanswerable`, or `ambiguous`
- `expected_answer`, `expected_source_ids`, `relevant_source_ids`,
  `distractor_source_ids`, and `required_evidence`
- `tenant_id` and deterministic `split`

Source identity is document-level in this preparation pass. The required
evidence list supports multi-document answers; near-miss and ACL-negative
records retain the relevant unauthorized/distractor source IDs while carrying
no expected evidence.

Categories cover standard and hard answerable cases, unanswerable and
near-miss cases, ambiguity, version/conflict resolution, cross-lingual lookup,
multi-document evidence, tenant ACL negatives, and injection-bearing relevant
documents. Language pairs include `tr->tr`, `en->en`, `tr->en`, `en->tr`, and
mixed-evidence multi-document cases.

## Splits and frozen-test policy

The deterministic split assigns whole `case_family` groups with a size-aware
stratification target of approximately 45% `development`, 25% `calibration`,
and 30% `frozen_test`. The current counts are 202 / 110 / 133 for 445
questions. A fact's paraphrases, near-miss variants, ACL variants, version
variants, and other intent variants cannot cross split boundaries. The split
metadata and frozen ID digest are in
`artifacts/evaluation-corpus-v2/dataset-metadata.json`.

Answerability threshold or model tuning must use development and calibration
only. `frozen_test` is reserved for a later, pre-registered evaluation run;
changing its intent or labels requires a new dataset fingerprint and review.
“Frozen” is a process and validation policy here, not a filesystem write
protection mechanism.

## Validation and fingerprints

Run the fast validator from the repository root:

```bash
.venv/bin/python -m scripts.validate_evaluation_corpus
```

The validator checks source paths, Markdown/PDF integrity, duplicate IDs and
normalized queries, valid split/language/answerability values, source
references, tenant boundaries, answerability evidence rules, category
coverage, split bands, and artifact consistency. It performs no model
inference and does not contact Ollama or Qdrant.

`statistics.json` contains static character/word percentiles, document and
question distributions, answerable-only language-pair counts, non-answerable
query-language counts, and split cross-tabs for answerability, primary
category, query language, tenant, and difficulty. Its all-record language-pair
counts include `none` for unanswerable/ambiguous records; the
`answerable_language_pair_counts` field is the language-pair view of the
answerable subset. It also contains a whitespace-proxy chunking dry-run for
256, 384, 512, and 768 targets. It is a structural pre-check, not a retrieval
metric.
`fingerprints.json` contains deterministic SHA-256 corpus and dataset
fingerprints over canonical metadata/text/records.

## Next benchmark run

`artifacts/evaluation-corpus-v2/benchmark-plan.json` is the execution manifest
for the next sprint. It fixes the current production controls—Qwen3-Embedding-
4B at 1024 dimensions, BM25 + dense + RRF, BGE reranking, candidate 20 → top
5, baseline 500/50, `answer_v3`, STRICT validation, and tenant ACL—while
leaving answerability strategy, token-aware chunking, and claim grounding as
future comparison axes. The manifest is intentionally not a result artifact.

This preparation pass did not run Recall/MRR/nDCG, reranker scoring, embedding
or generation, DeepEval, LLM judging, Ollama batch generation, Qdrant indexing,
or production reindexing.

## Known limitations

Labels are document-level rather than exact span-level, so citation-sensitive
span evaluation remains a follow-up. The documents are synthetic fixtures and
do not model every production connector or file format. Static wording review
reduces obvious template leakage, but semantic duplicate detection and model
quality remain intentionally deferred to the benchmark sprint.
