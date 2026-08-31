# Shadow isolation

All six direct-CDP UI runs returned a completed visible UI state. Each case
observed one `/chat` HTTP 200 response, zero fatal console errors, and zero
resource failures. Shadow telemetry was diagnostic-only; no visible answer,
SSE state, support-ID list, citation object, citation rendering, or
forced-abstain decision was mutated. No authoritative V2 execution occurred.

The existing deterministic shadow-isolation and authoritative fail-closed
tests also passed in the focused suite.
