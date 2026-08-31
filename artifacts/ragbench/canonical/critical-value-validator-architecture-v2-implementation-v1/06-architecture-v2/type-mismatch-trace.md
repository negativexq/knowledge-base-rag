# Type-mismatch trace

Answer: `The setting is 30. The retention is 30 days.`

| occurrence | raw | exact span | type | role |
|---|---|---:|---|---|
| typed.O1 | `30` | `[15,17)` | NUMBER | VALIDATE |
| typed.O2 | `30 days` | `[36,43)` | DURATION | VALIDATE |

The same normalized value does not join these occurrences. Type remains a V3
comparison attribute, not an occurrence identity key.
