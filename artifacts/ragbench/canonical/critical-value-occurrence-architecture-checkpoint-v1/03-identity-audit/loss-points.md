# Identity-loss audit

## Loss point 1: public extraction

`extract_critical_values()` returns `CriticalValue(kind, value, unit)` and no
span, raw literal, claim unit, or occurrence ID. It is suitable for historical
union-scope checks, not for occurrence-level decisions.

## Loss point 2: local token reconstruction

`_local_tokens()` adds temporary `start`/`end` fields, but the dictionaries are
mutable and have no immutable identity. `_v3_tokenized()` may mutate `kind`
based on context and may add/reclassify tokens. The same text can therefore
have different token populations and types at different passes.

## Loss point 3: role/value rejoin

V5's `_v5_same_surface_companion()` scans all token siblings by normalized
`value`. That is a useful context signal, but it is not an identity relation.
V4 additionally uses same `kind`/`unit` and different value as a companion
criterion. These conditions can identify that a contrast exists while failing
to identify which exact occurrence is the rejected premise.

## Loss point 4: masking boundary

V4, V5, and V6 create a masked string and then call the production V3 audit.
The V3 audit re-extracts the masked string. The original exact span and any
diagnostic occurrence ID are not passed into the comparison. This is the
strongest architectural source of boundary instability and sibling
contamination.

## Loss point 5: result aggregation

`validate_support_unit_answer()` stores the value audit inside a part-level
telemetry structure and decides whether the whole answer part survives. The
validator result reports counts and traces, but there is no first-class
occurrence result that the answer part can use to show which exact literals
were validated or excluded.

## Conclusion

The evidence supports a general occurrence abstraction and a structured
filter. Additional regex patches would leave the masking/re-extraction and
value/type rejoin boundaries intact.
