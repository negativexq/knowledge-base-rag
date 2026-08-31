# V4 candidate delta

V4 is a DEBUG-only challenger over frozen V3. It classifies deterministic rejected-premise occurrences and masks only those spans before delegating the remaining numeric, locale, identifier, and version checks to frozen V3.

Invariants: unknown/ambiguous polarity remains validated; substantive negation, quotation, comparison, signs, identifiers, locale safety, and version specificity are not globally suppressed. The production selector remains `baseline|v3`; V4 is not production-enabled.
