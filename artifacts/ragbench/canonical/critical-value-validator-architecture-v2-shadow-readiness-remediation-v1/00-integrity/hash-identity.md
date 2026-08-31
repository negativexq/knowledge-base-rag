# Hash identity

The two Architecture V2 hashes are intentionally different objects:

| Object | Algorithm | Bytes/object hashed | Meaning |
|---|---|---|---|
| Architecture V2 semantic/source digest | SHA-256 | The frozen Architecture V2 semantic source manifest object, as recorded by the frozen candidate identity | `CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1` identity: `09d94bb7c9d1769bd79e18c0beaa75c653477d3127605fdbcaddc5e9cf7ed33b` |
| Integration freeze manifest raw-file digest | SHA-256 | Raw bytes of `critical-value-validator-architecture-v2-production-integration-v1/00-integrity/source-hashes.json` | File/artifact digest: `c797556bff29669cdafdb165646b601e94ce4a1573969dd69b9e452f2d080d23` |
| Remediation contract digest | SHA-256 | Raw bytes of this task's `01-preregistration/remediation-contract.json` | Frozen remediation scope: `11021e0e172073be69b873c162f6291dd53444639f976e526b9928e28b8d7ade` |

The first value identifies frozen Architecture V2 semantics. The second
identifies a historical integration manifest file. They are not interchangeable
and no contradiction was found.
