# Source-grounded answer verification

Research recorded: 18 October 2026. This document explains evaluation and reviewer
design. Current implementation is described in the [agentic workflow](adaptive-workflow.md).
Published methods below are distinguished from this project's architectural choices.

## Decision

Give the generator a short task-focused contract. Evaluate source support,
question scope, completeness, and numeric correctness separately. Keep access
and evidence identity as code-enforced boundaries. Equivalent presentation is
not automatically a content error. Calibrate semantic reviewers with human-labeled
examples before changing release policy.

Gold answers are not inherently harmful. Treating one wording as the only valid
answer or as a runtime target is harmful. Reference similarity alone is also
insufficient: a plausible number may belong to the wrong company, period, or table.

## Published approaches

| Source | Documented approach | Design implication |
| --- | --- | --- |
| [Microsoft Foundry RAG evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators) | Separate grounding, relevance, reference completeness, and retrieval evaluation. | Do not hide failure types behind one pass/fail score. |
| [Ragas faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) and [factual correctness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/factual_correctness/) | Compare answer claims to sources, and answer/reference claims with precision/recall/F1. | Grounding and reference coverage have different meanings. |
| [TruLens RAG Triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/) | Context relevance, groundedness, and answer relevance. | Separate parser/retrieval loss from generation loss. |
| [DeepMind FACTS Grounding](https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/) | Request fulfillment and grounding are separate stages; multiple judge families and human evaluation are used. | Avoid rewarding vacuous answers. Its exclusion of complex maths limits direct transfer to financial ratios. |
| [LangSmith judge calibration](https://www.langchain.com/resources/llm-as-a-judge) | Track agreement and calibrate with human corrections. | A reviewer needs its own versioned test set and error measurements. |
| [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Clear principles, selective context, examples, and understandable tools. | Avoid adding another generator prohibition for every benchmark failure. |
| [Anthropic evaluation engineering](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Combine code, model, and human graders; distinguish capability and regression sets. | Evaluate outcomes and useful partial success without imposing one exact action sequence. |

These sources do not disclose every product's internal architecture. This note
uses their published methods rather than claiming a shared production approval flow.

## Three distinct contracts

1. **Generation:** answer the user's question from authorized evidence, cite
   sources, perform required computations, and explain material gaps or conflicts.
   No gold answer, benchmark row, or target reviewer score is provided.
2. **Runtime verification:** inspect the question, candidate, citations, necessary
   headers/context, and tool receipts. No gold answer is used. The generator's
   own explanation is not independent source evidence.
3. **Offline evaluation:** use the question, original sources, candidate, and
   versioned reference to measure correctness, completeness, usefulness, and
   unnecessary refusal. Incorrect references are reviewed and preserved by version.

Runtime completeness can be assessed against the question's subrequests. It
must not be represented as coverage of an unknown gold answer.

## Strict meaning and flexible expression

| Topic | Policy |
| --- | --- |
| Tenant, document permission, and source version | Hard application boundary; a judge cannot expand access. |
| Support ID validity | Code check; a real ID proves provenance, not entailment. |
| Company, product, period, population, row/column binding | Core semantic requirement. |
| Wording, translation, sentence order, list/summary style | Flexible unless the user explicitly requires a format. |
| 60 minutes / 1 hour; 1 meter / 100 centimeters | Equivalent when dimensions and context are preserved. |
| Billion / million and decimal separators | Resolve language, scale, source value, and canonical value explicitly. |
| USD / EUR | Requires exchange rate, date, and rate source. |
| Percent / percentage points | Generally different. |
| Rounding | Based on requested precision and source resolution, not a universal 1% tolerance. |
| Versions and identifiers | Do not normalize as ordinary numbers without a domain contract. |
| Tool access | Permission, capability, relevance, and budget; visual keywords alone are not enough. |
| Output schema | Small stable integration contract; do not force the user-facing answer into an unnecessary proof format. |

An explicit request for centimeters, JSON, or three decimal places is a genuine
task constraint. A hidden formatting requirement invented to match a benchmark
is a different matter.

## Verification flow

Preserve retrieval results with headings, table headers, and source identities.
Open neighboring context or original images when a relationship is missing.
The generator returns a natural answer with citations and computation receipts
where needed. Progress is not limited to adding another text block.

Split the answer into meaningful claims while retaining subject, period, unit,
negation, condition, and quantity bindings. The generator does not need to write
every sentence as a microscopic claim. Check each claim against its own citations
and necessary local context; finding the same number elsewhere is insufficient.

Use code for explicit arithmetic and permitted conversions. An unparseable free-form
number is a diagnostic issue, not automatically proof that the content is false.
For a material defect, give a bounded targeted correction identifying the claim,
source conflict, or missing relationship. Recheck the candidate actually released.

A conceptual reviewer receipt can include:

```json
{
  "claim_id": "C1",
  "support": "supported | contradicted | not_established | judge_error",
  "answers_requested_scope": true,
  "numeric_check": "equivalent | correct_derived | mismatch | not_applicable | unresolved",
  "evidence_ids": ["E1.S1"],
  "materiality": "core | ancillary",
  "reason_code": "NONE"
}
```

This is a design example, not a promised API schema. A reviewer/API error is
not a support decision. Model confidence percentages are not calibrated
probabilities. Checking a witness's literal presence is useful without requiring
the final answer to be a verbatim quotation.

## Release decisions

- Supported core answer: release; equivalent wording is not a rejection reason.
- Material contradiction: repair the affected claim, or do not release that claim.
- Insufficient evidence: seek justified additional evidence or provide explicit
  partial scope/clarification. A failed search alone does not prove absence.
- Reviewer uncertainty: use a bounded second check or inspection path. Do not
  automatically approve or mark the content false.
- Reviewer/API/budget failure: record a separate operational result. Do not score
  it as successful verification or justified epistemic abstention.

Removing an unsupported fragment can change a remaining claim's meaning.
Blindly deleting failed sentences is unsafe. Many correct peripheral claims
cannot average away one incorrect core result.

## Calibrating the reviewer

[MT-Bench / Chatbot Arena research](https://arxiv.org/abs/2306.05685) discusses
position, verbosity, and self-family preference biases. A strong judge, two
agreeing judges, or multiple model families do not replace human calibration.

Include human-labeled examples covering:

- Source-supported answers with equivalent wording, languages, units, and order.
- Correct numbers bound to the wrong entity, period, series, or percentage meaning.
- Correct maths on wrong inputs; wrong maths on correct inputs; legitimate rounding.
- Important missing subrequests and explicitly useful partial answers.
- Truly unanswerable questions and unnecessary refusals despite available evidence.
- Noisy OCR, lost headers, contradictory sources, and reviewer errors.

Meaning-preserving transformations should preserve the decision; changes to a
period, unit, or core quantity should trigger the appropriate error. Keep these
as evaluation tests rather than only prompt examples. Prefer independent human
annotations with reasoned adjudication. Split calibration and evaluation documents.
Required sample size depends on target error rates, subtypes, and confidence
intervals; an arbitrary initial count is not a reliability guarantee.

Blind generator identity and old/new labels where possible, randomize pairwise
order, and allow both candidates to be wrong. Measure repeated-judgment stability
and human disagreement on difficult examples.

## Metrics and denominators

| Metric | Numerator / denominator |
| --- | --- |
| Reviewer false rejection | Human-correct rejected candidates / human-correct candidates. |
| Reviewer false acceptance | Human-incorrect accepted candidates / human-incorrect candidates. |
| Published-answer error | Incorrect published answers / published answers. |
| Answerable-question coverage | Substantive answers / answerable questions; separate full and partial. |
| Supported end-to-end success | Correct, sufficient, grounded answers / answerable questions. |
| Unnecessary refusal | Answerable but unanswered / answerable questions; distinguish model, validator, and operational causes. |
| Incorrect answer to an unanswerable question | Substantive incorrect answers / unanswerable questions. |
| Cost and latency | Generation, research, review, correction, and their total. |

Reviewer false acceptance and published-error rate use different denominators.
Reducing errors by refusing more questions is not an improvement by itself;
compare error with supported answer coverage.

## Controlled adoption and overfitting prevention

1. Re-evaluate saved candidates with fixed question/evidence/answer before changing
   generation. More approvals are not proof of improvement without labels.
2. Run a new reviewer in shadow mode before replacing release decisions.
3. Separate producer and reviewer effects: compare old/simplified producer against
   old/new review under fixed evidence. Measure access/budget/effort changes separately.
4. Split known failures, calibration, and held-out evaluation by document. Another
   question from the same PDF is not a fully independent holdout.
5. Add counterexamples: accepting equivalent units must still reject wrong units,
   currency, period, and series. Include unanswerable regressions.
6. Record models, references, evidence, prompt/reviewer versions, randomness,
   budgets, repeated runs, and paired differences. Account for document dependence.
7. Set product acceptance criteria before seeing final evaluation results.

The known 62-question set is development/regression material. Earlier parser
investigations also used old answers/pages, so label and source-page versions
must be pinned. Corrections retain previous reports and are not model gains.

## Repository mapping

The original investigation targeted progress/finalization in `agentic.py`, numeric
presentation versus meaning in `structured_output.py`, semantic scope and review
errors in `scope_validation.py`, and budget/finalization outcomes in
`research_budget.py`. It proposed human calibration on saved candidates before
broad prompt or release changes.

The implemented [adaptive workflow](adaptive-workflow.md) now adds typed state,
source-grounded objections, separate input/coverage/operation assessments,
bounded targeted repair, original-page routing, and preserved computations.
Those controls do not eliminate semantic reviewer error; broader calibration
and held-out evaluation remain necessary.
