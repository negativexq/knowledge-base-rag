# Backward compatibility

Architecture V2 can reuse the existing parsed support-unit output and
authorized support-unit boundary. No request, response, SSE, citation,
support-ID, frontend, database, Qdrant, indexing, or embedding schema change
is required.

The future implementation surface is internal:

1. extend the server-side selector allow-list;
2. add an adapter in support relevance/structured validation;
3. pass immutable occurrence/role results to the frozen V3 comparison
   primitives;
4. add optional isolated shadow execution and bounded telemetry;
5. preserve baseline default and config rollback.

The structured-output schema remains unchanged.
