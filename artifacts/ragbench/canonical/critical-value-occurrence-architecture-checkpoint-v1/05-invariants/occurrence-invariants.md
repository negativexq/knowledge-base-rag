# Occurrence invariants

These are proposed frozen design invariants for V7, not implementation claims.

| ID | Invariant |
|---|---|
| I1 | Different spans are different occurrence identities. |
| I2 | Same normalized value does not imply shared role. |
| I3 | The role layer cannot rediscover occurrences via substring search. |
| I4 | A nested non-extractor-owned substring is not an independent occurrence. |
| I5 | A signed literal owns its sign. |
| I6 | A duration owns its unit-bearing extent. |
| I7 | A version owns the canonical extractor span. |
| I8 | An identifier owns the canonical identifier span. |
| I9 | Ambiguous role maps to VALIDATE. |
| I10 | A real factual assertion cannot be skipped because a sibling is rejected. |
| I11 | Role assignment is claim-local. |
| I12 | Role decisions cannot mutate occurrence identity. |
| I13 | There is no global normalized-value mask. |
| I14 | No re-extraction follows polarity filtering when structured filtering is feasible. |
| I15 | V3 comparison semantics remain unchanged. |

## Boundary examples

`-204` owns the sign; a later standalone `204` is a separate sibling. `8.1.2`
owns its full version span; `8.1` inside it is not a sibling. `30 days` owns
the number and unit; a bare `30` is not recreated from that span. `CVE-2025-1234`
owns the identifier body and does not emit a suffix `1234` occurrence. A
substantive negative claim such as “does not expire after 90 days” remains a
validation obligation; nearby negation is not a skip rule.
