# TECHQA Amendment Provenance Reconciliation V1

## Result

Primary verdict: `AMENDMENT_V1_PROVENANCE_INCONCLUSIVE`

Current v1 raw SHA256: `2cea26bfda90d3f1861e575a5bdd34c6889506948beb3cba30313b9f26c210c4`  
Current sidecar SHA256: `2cea26bfda90d3f1861e575a5bdd34c6889506948beb3cba30313b9f26c210c4`  
Historical reported SHA256: `dd4310b1717a16733e765de3c1d7fa76c9b58cddde43750e2f3bf4d4410b2fe8`

The current JSON and sidecar match under the raw-file-byte convention. None
of the legitimate representations tested (raw bytes, UTF-8 bytes, LF-normalized
bytes, sorted compact JSON, sorted pretty JSON, and trailing-newline variants)
produces the historical value. The historical value appears nowhere as a v1
file or sidecar hash in the permitted scan scope; it appears only as an
expected-value field in the prior blocker artifact. No earlier v1 byte copy is
recoverable.

The creation code uses a dynamic `created_at` and rewrites the v1 file before
hashing it. Therefore the code path is raw-byte consistent per execution but
the v1 identity is mutable across reruns. This explains why a stale hash is
possible, but does not prove whether `dd4310…` was a prior v1 hash, a value
from another representation/path, or a reporting transcription.

The current amendment is not semantically complete as a future immutable
execution contract: it omits explicit frozen statements for chunking,
embedding/retrieval, SectionAware, Luna, validators, and the complete blind
review procedure. Because the provenance verdict is inconclusive, no v2 was
created under the fail-closed rule.

HOLDOUT content accessed by this task: **NO**  
Arm maps opened: **NO**  
Provider calls: **0**  
Original v1 files modified: **NO**
