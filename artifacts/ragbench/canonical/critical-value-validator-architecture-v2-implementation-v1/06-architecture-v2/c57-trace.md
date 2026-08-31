# C57-like trace

Answer: `The signed result is -204, not 204.`

| occurrence | raw | exact span | type | role |
|---|---|---:|---|---|
| c57.O1 | `-204` | `[21,25)` | SIGNED_NUMBER | VALIDATE |
| c57.O2 | `204` | `[31,34)` | NUMBER | SKIP_REJECTED_PREMISE |

There is no independent `204` occurrence inside `[21,25)`. The ledger owns the
sign and uses the extractor-owned spans. The filtered V3 input contains only
`c57.O1`; no raw answer masking or post-role extraction occurs.
