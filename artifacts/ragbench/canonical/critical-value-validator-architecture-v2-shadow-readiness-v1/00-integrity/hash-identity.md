# Hash identity

| Object | Algorithm | Bytes/object | Meaning |
|---|---|---|---|
| Architecture V2 semantic/source digest | SHA-256 | The frozen architecture manifest's declared semantic digest over the frozen implementation source manifest | `09d94bb7c9d1769bd79e18c0beaa75c653477d3127605fdbcaddc5e9cf7ed33b` identifies Architecture V2 semantics/source identity. |
| Architecture V2 freeze manifest raw file | SHA-256 | Raw UTF-8 bytes of `03-implementation/final-source-freeze.json` | `c797556bff29669cdafdb165646b601e94ce4a1573969dd69b9e452f2d080d23` identifies that manifest file, not the semantic source digest. |
| Shadow-readiness protocol | SHA-256 | Raw UTF-8 bytes of `01-runtime-plan/shadow-readiness-protocol.json` | Frozen runtime scope and gates for this task. |

The two Architecture V2 hashes are therefore not interchangeable. The first
is the declared architecture/source identity; the second is the raw bytes
hash of the prior freeze-manifest artifact.
