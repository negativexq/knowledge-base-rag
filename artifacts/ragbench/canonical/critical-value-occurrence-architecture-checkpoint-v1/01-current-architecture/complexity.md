# Complexity and dataflow comparison

The repository does not expose a single instrumentation counter for every
internal regex invocation, so the table distinguishes directly observable
passes from repeated helper work. Counts are per claim unless noted.

| operation | current V4–V6 shape | proposed V7 shape |
|---|---|---|
| claim extraction | V4/V5/V6 candidate construction, plus downstream V3 extraction after masking | one canonical extraction pass |
| role text scans | clause/sentence windows and full-answer sibling scan; repeated by occurrence | one role pass over immutable occurrences and bounded context |
| support extraction | production baseline may tokenize support repeatedly inside answer-token/support loops | one evidence occurrence snapshot reused by validation |
| value remaps | normalized value/type/unit comparisons at each reconstruction; V6 also preserves raw span separately | normalization attached once to each occurrence; comparison uses occurrence ID plus value fields |
| masking | zero or one length-preserving whole-answer masking pass in each debug helper | none on the preferred structured path |
| re-extraction | yes after any rejected-premise mask, through frozen V3 | zero |
| identity transport | temporary dict identity; V6 `O1..On` only in debug result | immutable ledger ID carried through role and validation |

## Directly evidenced current passes

The production baseline calls `_local_tokens(claim)` once and then invokes
`_local_tokens(support_text)` inside the answer-token loop. `_v3_relation_audit`
creates claim and support token arrays again. V4 creates a V3 token array,
masks, and may create another V3 token array. V5 and V6 add their own token
construction and may again call V3 on the masked claim. Exact runtime counts
vary with number of support units and whether a guard applies, but the
identity-relevant fact is invariant: the masked string is a new extraction
input.

## Proposed complexity goal

V7 should reduce the number of identity-bearing extraction passes and eliminate
mask/re-extract. It may use bounded local-context slicing, but that slicing
must never emit a new occurrence. This is a simpler dataflow, not a request to
remove V3 safety checks or to optimize unrelated retrieval work.
