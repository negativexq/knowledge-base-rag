# TECHQA Corrected HOLDOUT Amendment V2

Status: `CORRECTED_HOLDOUT_EXECUTION_AUTHORIZED_BY_AMENDMENT_V2`

V2 is a new immutable authorization artifact. Amendment v1 remains
`INVALID_FOR_AUTHORIZATION` and was not modified. The original HOLDOUT run
remains invalid due to `HOLDOUT_RUN_INVALID_CORPUS_SCOPE`.

Authoritative v2 SHA256 (exact raw file bytes): `22da15d58b5e29bacd3a5593f0d40a14c9c81e84b54f69179341cbdf865326a4`

The v2 writer created the JSON once with `O_EXCL`, closed it, hashed the exact
bytes, wrote the sidecar once, and verified the pair again at the end. The JSON
contains no self-referential final hash. Recreating the same target fails with
`AMENDMENT_V2_ALREADY_EXISTS`.

The only authorized benchmark correction is corpus scope: use the deterministic
proper pinned TechQA source-document corpus, with the existing chunking,
embedding, retrieval, reranking, evidence, generator, validator, retry, and
blind-review designs explicitly frozen in the JSON.

No HOLDOUT content was accessed by this task. No retrieval, embedding, BGE,
Luna, or Terra calls were made. Corrected HOLDOUT execution was not run.
