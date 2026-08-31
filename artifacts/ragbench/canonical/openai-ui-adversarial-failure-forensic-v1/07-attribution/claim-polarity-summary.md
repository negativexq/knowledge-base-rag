# Claim polarity summary

Scope: T3, T4, and T5 only. This is a reconstruction from the frozen UI
summary and bounded validator trace tags. Raw model answers, extracted model
claims, and final evidence snapshots were not persisted.

| Question | Correct raw correction confirmed | Wrong premise mentioned only to reject confirmed | Polarity blindness proven | Status |
|---|---:|---:|---:|---|
| T3 | 0 | 0 | 0 | INCONCLUSIVE |
| T4 | 0 | 0 | 0 | INCONCLUSIVE |
| T5 | 0 | 0 | 0 | INCONCLUSIVE |

Confirmed correct raw corrections: **0**. Cases rejected because of a
wrong-premise mention: **0 proven**. Cases proving polarity blindness:
**0**. Inconclusive cases: **3**.

The traces prove T3/T5 direct conflict and T4 indeterminate handling followed
by forced abstention. They do not prove whether the model's raw output was a
corrective answer such as “30 days is incorrect; 90 days is documented”, or a
positive unsupported assertion. No `CLAIM_POLARITY_FALSE_CONFLICT` case is
confirmed by the available artifacts.
