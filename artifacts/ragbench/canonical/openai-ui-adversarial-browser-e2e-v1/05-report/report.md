# OpenAI UI Adversarial Browser E2E V1

## Scope

This is a local Chrome CDP adversarial smoke test, not a benchmark or a
production accuracy claim. The frozen 18-case matrix was executed once after
the matrix hash was recorded. RAG V2 and support-ID generation were enabled
only through runtime environment overrides. The authoritative validator stayed
`baseline`; V3 remained shadow-only.

The existing `OpenAIGeneratorClient` was already a strict Responses API
adapter used by tests/evaluation. Production support was partial because the
server selector accepted only `ollama|claude`; the selector now accepts
`openai` and uses the existing adapter. The committed default remains Ollama.

## Runtime

- Provider: OpenAI Responses API
- Model: `gpt-5.6-luna`
- API key: available through the server environment; value was never printed or persisted
- RAG V2: enabled
- Support IDs: enabled
- Validator: baseline
- V3 shadow: enabled
- OpenAI generation calls: 18
- Retrieval embeddings: unchanged Ollama path

## Results

All 18 browser requests returned HTTP 200 `text/event-stream`, completed, and
had no failed network requests or meaningful browser console errors.

Adjudication counts:

- CORRECT: 9
- PARTIAL: 0
- INCORRECT: 4
- UNAVAILABLE_EXPECTED: 5
- UNAVAILABLE_UNEXPECTED: 0

Valid application-owned support IDs were rendered for 9 grounded answers.
Missing, wrong, and fake citation counts were 0. The fake `[E99.S99]`
request did not become an accepted citation; the response used valid `[E1.S2]`.

The four incorrect outcomes were T3, T4, T5, and T6. T3/T4/T5 were
conservative unavailable outcomes associated with critical-value conflict or
indeterminate traces. T6 was unavailable with no visible answer/citation;
the available trace evidence is insufficient to assign a more specific cause
than retrieval/evidence availability.

T8 and T12 included an extra source-like string in model text in addition to
valid support IDs. This did not create a fake accepted support ID or expose
hidden evidence, but it is an output-contract observation for future review.

## Shadow and security

Representative Jaeger traces showed validator invocation, bounded reason
class, critical-value type, forced-abstain status, baseline duration, V3
shadow duration, `shadow_disagreement=SAME`, and `shadow_error=false`. The
baseline result remained authoritative. No raw query, claim, support text,
document content, prompt, or secret was persisted in telemetry artifacts.

No unauthorized support acceptance, fake support-ID acceptance, prompt/system
prompt leakage, API 4xx/5xx, CORS failure, or SSE failure was observed.

## Conclusions

- STACK_E2E: PASS
- OPENAI_PROVIDER_E2E: PASS
- SUPPORT_ID_PIPELINE: PASS
- CITATION_RESOLUTION: PASS for observed grounded answers
- SECURITY_E2E: PASS
- V3 shadow: PASS; 17 observed validator comparisons were `SAME` and one
  bounded disagreement was `BASELINE_PASS_V3_IND` (T10). The baseline result
  remained authoritative.
- Adversarial semantic quality: mixed; conservative suppression occurred on 4 cases

No V3 tuning, retrieval tuning, prompt change, BGE change, Top-N change,
HOLDOUT use, commit, or push was performed.
