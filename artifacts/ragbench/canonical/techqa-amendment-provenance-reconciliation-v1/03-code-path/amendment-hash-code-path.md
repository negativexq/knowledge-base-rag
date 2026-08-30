# Amendment v1 hash code path

`audit_techqa_holdout_measurement_validity_v1.py` constructs a new amendment object,
sets `created_at` with `datetime.now(UTC).isoformat()`, writes the pretty JSON with a
trailing LF, then reads those exact bytes and writes the sidecar SHA256. There is no
hash-before-final-write, wrong-variable, temporary-path, or post-write formatting step
in this code path.

The provenance defect is mutability: rerunning the audit reconstructs v1 with a new
timestamp and rewrites the same v1 path. Each individual write/hash sequence is raw-byte
consistent, but the v1 identity is not stable across reruns. The historical `dd4310...`
value is not present in the v1 JSON or sidecar and no prior v1 bytes are recoverable in
the permitted repository/task artifact scope.
