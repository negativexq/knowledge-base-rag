# C50-like trace

Answer: `The old limit was 100. The 100 in your question is wrong; current limit is 120.`

| occurrence | raw | exact span | role |
|---|---|---:|---|
| c50.O1 | `100` | `[18,21)` | VALIDATE |
| c50.O2 | `100` | `[27,30)` | SKIP_REJECTED_PREMISE |
| c50.O3 | `120` | `[75,78)` | VALIDATE |

The two `100` values have distinct IDs and independent decisions. The V3
filtered set is `c50.O1,c50.O3`; no value-level mask is constructed.
