# Future integration test plan

Required reusable tests before any integration implementation is activated:

- baseline remains the default;
- explicit `architecture_v2` is server-side only;
- invalid selector fails closed;
- shadow does not change authoritative outcome;
- shadow failure does not change user response;
- forced-abstain policy remains unchanged;
- support-ID authorization and citation ownership remain unchanged;
- request/response/SSE schemas remain compatible;
- config-only rollback works;
- local forensic capture contains ledger/roles/filter when explicitly enabled;
- OTel contains bounded metadata only;
- frozen V3 delegation is outcome-equivalent for identical validate inputs.

The current focused Architecture V2 tests are green and the current full
deterministic suite is green. No provider or retrieval test is required for
this design review.
