# Claim polarity summary

- T3: **YES**. The raw answer correctly states 90 days and mentions 30 days only as the rejected premise (`not 30 days`). The baseline extracts 90 as direct support and 30 as direct conflict; this causes forced abstention.
- T4: **INCONCLUSIVE** under the strict rule. The raw answer correctly rejects 500 and states 120. The current extractor selects the leading `No` as a BOOLEAN token and does not extract the numeric 500 in this path; the recorded indeterminate is therefore not proven to be caused by treating 500 as a positive support obligation.
- T5: **YES**. The raw answer correctly states 120 and mentions 100 only as a rejected alternative (`not 100`). The baseline extracts 120 as direct support and 100 as direct conflict, causing forced abstention.

Confirmed high-confidence `CLAIM_POLARITY_FALSE_CONFLICT` cases: **2 (T3, T5)**.

The capture's literal arrays are redacted by the existing safety redactor because their field names contain `token`; exact occurrences above were deterministically reconstructed from the immutable captured raw answer/support text with the same local parser, without provider calls.
