# Canonical RAGBench record

The pinned eManual Basic-50 run is a descriptive Basic-RAG baseline, not a
replacement for the custom security and stress suites. It uses the production-
compatible hybrid retrieval and multilingual reranking path, with Luna at
`reasoning=none`.

The graceful SectionAware policy eliminated ordinary budget assembly failures
without changing the 1200-token budget. The semantic audit found 29 correct,
7 partial, 4 incorrect visible answers, and 10 abstentions. Retrieval-stage
sentence recall was 100% at hybrid Top20, 96.24% mean at BGE Top5, and 89.72%
after SectionAware assembly.

The sentence-ID citation direction is retained as a planned feature: the
four-query challenger selected valid request-scoped IDs in 4/4 cases and
recovered 3/4 semantic answers, but this is not broad production validation.
