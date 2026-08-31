# Architecture V2 invariant audit

The final deterministic execution used 103 cases and 195 occurrence labels.
The reusable test suite passed 45 focused tests. The following status is based
on source inspection, focused tests, and the frozen final execution.

| invariant | status | evidence |
|---|---|---|
| I1 different spans are different identities | IMPLEMENTED / TESTED / PASS | frozen dataclass IDs are ordinal within claim and span fields are retained |
| I2 same normalized value does not share role | IMPLEMENTED / TESTED / PASS | C50-like and same-value tests |
| I3 role layer cannot rediscover by substring | IMPLEMENTED / TESTED / PASS | classifier consumes occurrence tuple only |
| I4 nested non-owned substring is not independent | IMPLEMENTED / TESTED / PASS | V6 lexical ownership is the extraction base |
| I5 signed literal owns sign | IMPLEMENTED / TESTED / PASS | C57 focused test |
| I6 duration owns unit-bearing extent | IMPLEMENTED / TESTED / PASS | duration extraction and typed trace |
| I7 version owns canonical span | IMPLEMENTED / TESTED / PASS | version focused test and V3 equivalence |
| I8 identifier owns canonical span | IMPLEMENTED / TESTED / PASS | SQLCODE/CVE focused coverage |
| I9 ambiguous role validates | IMPLEMENTED / TESTED / PASS | ambiguous focused test and six AMBIGUOUS labels |
| I10 sibling rejection cannot suppress factual sibling | IMPLEMENTED / TESTED / PASS | structured IDs and mixed-role cases |
| I11 role assignment is claim-local | IMPLEMENTED / TESTED / PASS | claim ID plus span-local context |
| I12 role cannot mutate identity | IMPLEMENTED / TESTED / PASS | frozen dataclass test |
| I13 no global value role mask | IMPLEMENTED / TESTED / PASS | no value set in V2 path; comparison trace |
| I14 no post-filter re-extraction when structured filtering is feasible | IMPLEMENTED / TESTED / PASS | V2 flags and adapter input contract |
| I15 V3 comparison semantics remain unchanged | IMPLEMENTED / TESTED / PASS | all-population V3 equivalence: 0 mismatches |

The legacy failures are explained by the boundary between role filtering and
V3 re-entry, not by retrieval or provider behavior. V2’s remaining corrective
misses are conservative classifier limits, not identity collapse; they do not
produce unsafe assertion skips in the final run.
