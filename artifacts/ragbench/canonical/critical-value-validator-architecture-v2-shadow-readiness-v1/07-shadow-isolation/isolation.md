# Shadow isolation

Deterministic integration tests passed for baseline + V2 shadow and v3 + V2
shadow. They verify that enabling the diagnostic shadow preserves the
authoritative validator outcome and failure codes.

The same-request controlled HTTP path completed normally with baseline as the
authoritative validator. No support-ID, citation, forced-abstain, or HTTP/SSE
mutation was observed at the API boundary. A browser-visible mutation count
cannot be independently asserted because the Chrome control connector was
unavailable; this is why the stack E2E gate remains failed.
