# Locale ambiguity contract

V2 preserves deterministic normalization only when local text establishes the
interpretation. Explicit technical integer contexts such as byte, record,
row, packet, or block counts may establish grouped-integer notation when the
grouped and unpunctuated forms have the same digits.

Trailing-zero decimal equivalence is allowed only for explicitly decimal
contexts such as duration, percentage, ratio, latency, or probability. `1.5`
and `15` are never equivalent.

Forms such as `1.000` versus `1000`, `1,000` versus `1.000`, and `2.500`
versus `2,500` remain `INDETERMINATE` without deterministic local
disambiguation. Locale is never inferred from tenant, language, benchmark, or
geography.

Signs remain material: `-204` is not `204`. Version family compatibility
remains distinct from exact-version equality. No global evidence search or
semantic entailment is introduced.
