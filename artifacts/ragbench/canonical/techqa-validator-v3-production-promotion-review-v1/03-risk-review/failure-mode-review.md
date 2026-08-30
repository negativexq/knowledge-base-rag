# Failure-mode review

The frozen V3 contract remains narrow and deterministic:

| Condition | Outcome | Safety posture |
| --- | --- | --- |
| Ambiguous locale-dependent numeric punctuation | `INDETERMINATE` | conservative; no locale guesser |
| Ambiguous exact-versus-family version wording | `INDETERMINATE` | conservative; no prefix broadening |
| Claim-local critical conflict | `REJECT` | fail closed |
| Missing or unsupported comparable literal | `INDETERMINATE` | no unsupported acceptance |
| Conflicting support literals | `REJECT` or `INDETERMINATE` according to the frozen relation result | preserve frozen deterministic behavior |
| Authorization, hidden, spoofed, or cross-tenant failure | `REJECT` / fail closed | security remains independent |

The two residual false positives are `IV3-EQ-16` (12.00 hours versus 12
hours) and `IV3-EQ-17` (100.0% versus 100%). Both are availability-only
representation gaps. Neither is an unsafe acceptance or a security bypass.
