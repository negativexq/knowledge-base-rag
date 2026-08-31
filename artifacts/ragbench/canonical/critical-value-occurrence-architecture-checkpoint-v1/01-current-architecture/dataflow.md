# Current critical-value dataflow

## Scope

This is a read-only architecture audit. No V7 code or production semantic
change is introduced. The current production selector remains `baseline|v3`;
V4, V5, and V6 are debug-only helpers appended to the same module.

## Production path

`claim_local_critical_value_audit()` validates the server-selected version.
The baseline path calls `_baseline_claim_local_critical_value_audit()`, which
calls `_local_tokens(claim)` and tokenizes each support unit. The validator
then compares token dictionaries by `(kind, value, unit)` and local-context
word overlap. The V3 path preserves baseline data but runs `_v3_status()`,
which performs additional version, signed-number, locale, identifier, and
relation checks. The returned result contains token traces, but no stable
immutable occurrence identity.

The production consumer is `audit_support_relevance()` in
`app/evidence/support_relevance.py`. The primary answer consumer is
`validate_support_unit_answer()` in `app/llm/structured_output.py`; it calls
the production audit for each model answer part and releases only valid
support units to the renderer. This is why a validator reject can become an
application abstain.

## Debug challenger path

The historical progression is:

```text
V4:  _v3_tokenized
     -> classify token dictionaries
     -> mask rejected spans
     -> re-tokenize masked text in frozen V3

V5:  _v5_tokenized (V3 tokens + bare numeric siblings)
     -> V4/V5 full-answer same-surface sibling scan
     -> mask exact spans
     -> re-tokenize masked text in frozen V3

V6:  _v5_tokenized
     -> add sign/full-identifier spans and overlap filtering
     -> assign diagnostic O1..On IDs
     -> reuse V5 role classifier
     -> mask exact spans
     -> re-tokenize masked text in frozen V3
```

V6 improved lexical extraction boundaries, but its `occurrence_id` exists only
in the returned debug dictionaries. It is not the identity consumed by the
delegated V3 validator. The downstream validator receives a new string and
reconstructs new token dictionaries.

## Important distinction

No raw `.find(value)` or `str.replace(value, ...)` was found in the V4–V6
masking helpers. Nevertheless, V5 role classification performs a full-answer
same-normalized-value sibling scan, and all V4–V6 implementations mask text
and then re-extract it. Those two operations are structurally equivalent to
identity rejoining: span-local diagnostic identity is not carried across the
validation boundary.

## Canonical boundary proposed for V7

```text
raw model answer
  -> one canonical extractor
  -> immutable occurrence ledger
  -> occurrence-local role decisions
  -> structured VALIDATE-occurrence filter
  -> frozen V3 normalization/comparison semantics
```

The proposed boundary changes identity transport only. It does not change V3
comparison semantics, prompts, retrieval, BGE, evidence selection, or the
production selector.
