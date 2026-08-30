# CODEX_BLIND_REVIEW

This is a blinded Codex semantic review of the existing Candidate A/B pack.
The arm map was not read. No previous arm-level results were used.

## Review method

All 50 candidates were scored independently against the question and the
provided reference/gold answer. Visible application output determines the
primary label; raw content is not used to upgrade an unavailable candidate.
Provided evidence was used only for grounding checks. Valid support IDs were
not treated as proof of semantic correctness.

## Blinded aggregate

| Candidate | CORRECT | PARTIAL | INCORRECT | UNAVAILABLE |
|---|---:|---:|---:|---:|
| A | 15 | 12 | 7 | 16 |
| B | 23 | 6 | 5 | 16 |

| Pair preference | Count |
|---|---:|
| A_BETTER | 6 |
| B_BETTER | 14 |
| TIE | 28 |
| BOTH_BAD | 2 |

These are Candidate A/B aggregates only; no arm-level interpretation is made.

## Confidence flags

### HIGH_CONFIDENCE

Direct reference matches, clear abstentions, clear wrong-entity answers, and
clear critical-value mismatches were high confidence. This includes Q015,
Q019, Q021, Q030, Q049, Q061, Q066, Q081, Q103, Q104, Q115, Q135, Q137,
Q139, Q150, Q168, Q170, Q180, Q231, Q249, Q256, Q266, Q270, Q278, Q284,
Q292, and Q307.

### MEDIUM_CONFIDENCE

Q007, Q016, Q020, Q022, Q043, Q052, Q063, Q069, Q072, Q084, Q093, Q096,
Q101, Q105, Q106, Q199, Q209, Q210, Q215, Q266, and Q305 involve partial
coverage, reference granularity, or technically scoped guidance.

### LOW_CONFIDENCE

Q042, Q139, and Q150 have reference/context wording that is itself sparse or
inferential. Both candidates are unavailable on the visible-output rubric, so
the resulting label is unchanged by that uncertainty.

## Second-pass consistency audit

No score changes: **NONE**.

The second pass checked unavailable-vs-incorrect preference, partial-vs-correct
thresholds, multi-fact answers, negative/absence claims, and critical values.
No change was made merely to balance Candidate A/B counts.

## Scope and safety

- Original `blind-scorecard.csv` was not modified.
- Semantic arm identity remains unknown.
- No unblinding was performed.
- No production, retrieval, generation, judge, or holdout operation was run.
