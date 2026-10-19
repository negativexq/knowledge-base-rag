# Two new questions: evidence recovery and an unresolved financial ratio

## Findings

Row 223 successfully found the missing high-income age-group evidence and published 90%,42%,39%. Row 1018 abstained although the original PDF contained the inputs for debt/EBITDA. Tool/source selection failed to gather and connect the required financial inputs.

The result is 1/2 for this pair; together with the preceding two known questions it was 3/4 on that implementation, not a benchmark score. The ordinary read/search remediation retained task-specific context and reused existing authorized document access rather than changing embeddings or retrieval parameters. It did not by itself solve Costco.

## Recorded main runs

| Row | Published response | Seconds | Model requests | Tool attempts | Reviewer support flag |
| --- | --- | ---: | ---: | ---: | --- |
| 1018 | I could not find this in the document. | 33.84 | 6 | 2 | False |
| 223 | ["90%","42%","39%"] (go online, own a smartphone, own a tablet computer, respectively; higher-income seniors are those with household income of $75,000+). [E6.S1] | 46.42 | 9 | 4 | True |

## Scope and records

These are selected development diagnostics scoped to the source document, not
an open-corpus retrieval score or a complete benchmark. A reviewer support flag
alone is not a success: an abstaining response is not counted as a published
answer. See the findings for source correctness, formatting differences, and
any limitations of the review packet. Main generation did not receive gold
answers; separate diagnostic review occurred afterward.

Reported main-run latency excludes dependency loading and separate PDF review.
Model usage is recorded in local result files; reviewer usage is separate.
A null cost field means prices were not configured, not that calls were free.
Historical price estimates, where stated, are not current pricing or billing.

The underlying measurements, source snapshots, full typed state, model outputs,
spans, profiles, and independent reviews remain unchanged in local run folders.
Raw JSON/JSONL, images, captures, source capsules, and original-language report
backups are ignored by Git. This English summary retains the outcome and main
failure mechanisms; later successful runs do not overwrite earlier failures.
