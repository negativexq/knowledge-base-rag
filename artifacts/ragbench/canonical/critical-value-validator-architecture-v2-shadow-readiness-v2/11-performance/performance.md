# Performance

Architecture V2 shadow durations from the six actual Jaeger aggregate spans
were: 0.765, 2.506, 2.676, 2.983, 4.003, and 8.720 ms.

Local sample summary: p50 approximately 2.676 ms, p95 approximately 7.541 ms,
max 8.720 ms. This is a six-request local observation, not a production
benchmark. No material blocker or unbounded behavior was observed. Provider,
retrieval, and reranking costs dominate full browser request latency.
