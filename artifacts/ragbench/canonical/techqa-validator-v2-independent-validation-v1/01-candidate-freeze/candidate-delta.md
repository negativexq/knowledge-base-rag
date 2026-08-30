# Frozen V2 candidate delta

The candidate is the exact experimental `v2.v2_status` path from the DEBUG
V2 script. It composes the existing numeric, version, identifier, and negative
claim handling with `LOCALE_AMBIGUITY_GUARD`.

The guard leaves unambiguous technical grouped integers available when local
units establish grouping, permits trailing-zero decimal equivalence only in
explicit decimal contexts, and returns `INDETERMINATE` when punctuation can
change magnitude and local evidence cannot resolve its role.

Signs remain material (`-204` is not `204`); SQLCODE and CVE identities remain
claim-local; version-family compatibility remains distinct from exact-version
equality. No global evidence search, semantic entailment, security-policy
change, or production default change is included.

This file and the source hashes freeze the candidate before validation. Any
relevant source mutation requires a new candidate version.
