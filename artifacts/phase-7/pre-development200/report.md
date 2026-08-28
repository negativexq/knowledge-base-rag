# Pre-Development200 Measurement Freeze

This is a zero-inference audit. Generation, retrieval, embedding, and reranker calls: **0**.

## Smoke36 scoring audit

The authored rubric marks the four ambiguous records `SHOULD_CLARIFY`; the general factual-completeness metric is not applicable to them. Existing outputs were 0/4 clarified, 1/4 safely abstained, and 3/4 answered. The old metric is preserved and behavioral metrics are added in the scoring amendment.

The two injection records are answerable. Their 0/2 task completeness is a genuine content result, while injection resistance succeeded 2/2 and injection failures remained 0.

## Transport provenance

Smoke36 contains 36 official records from 37 transport attempts. The extra attempt was `cross-07-0`: the provider completed, but the scorer failed before atomic record persistence. The first raw output is not recoverable; no claim of raw-output identity is made.

## Selected V2.2 limitations

Corrected holdout attribution was 15 correctly attributed versus 10 misattributed visible outputs (40% of that combined set). Citation identity and ACL enforcement are deterministic, but semantic attribution is not guaranteed. Smoke36 multi-document completeness was 1/3 and remains a known weak slice.

## Development200 freeze

The deterministic 30-query attribution sample and measurement plan are frozen before inference. Final V2.2 config fingerprint: `680ca44af8b296526bd22b7d81a5388c59132da4fd42ff4f4cb968c2b1c2158d`. Development200 was **not started**.
