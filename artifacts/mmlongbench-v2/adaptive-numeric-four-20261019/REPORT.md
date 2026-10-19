# Typed numeric input: four-question recheck

Frozen sequential run on 19 October 2026, branch `fix/research-evidence-completion`,
based on `fd3d5ec`. Only the four requested NUM-001 failures were rechecked.
GPT-6 Luna, fast path, evidence needs and independent after-run review remained
enabled. Shared limits remained 10 requests, 120,000 tokens and 240 seconds.
Runtime hashes were checked before every question. Retrieval and embeddings did
not change; generation received neither gold answers nor reference-page hints.

| Row | Published result | Main time / requests | Finding |
| --- | --- | --- | --- |
| 471 | Abstention | 69.34 s / 5 | Completed checked absence: null, `not_found`, accepted coverage, no numeric conversion exception. Original page 19 lists green, white and caramel, without yellow. |
| 1026 | Abstention; answerable miss | 54.67 s / 4 | Draft preserves `(495)` and magnitude convention, but canonical notation rejects accounting parentheses. The independent checker then terminates with `ModelAPIError`; no returned assessment exists to checkpoint. The API failure is the immediate stop, distinct from the numeric contract defect. |
| 1025 | Abstention; answerable miss | 45.66 s / 5 | `(1,358)` and its requested magnitude survive extraction and accepted review. `shares (000s)` is incorrectly rejected as a source-scale mismatch. The normalization defect prevents execution. |
| 388 | Abstention | 67.43 s / 9 | Initial partial last-page evidence is rejected. Bounded completion and image inspection produce accepted full-page absence, preserved independently of finalization. No numeric conversion exception. |

Two source-consistent refusals now finish cleanly; two answerable financial
questions remain unresolved. All four previously problematic display/absence
strings survive as typed receipts rather than escaping Decimal exceptions.
That exception-handling improvement is not equivalent to four successful answers.

Main-pipeline time totals 237.10 seconds. Sequential wall time including startup
and after-run reviews is 373.41 seconds. Main usage totals 23 requests, 80,927 input
tokens and 9,633 output tokens. Dollar cost is unavailable because price metadata
is not configured; usage excludes separate review calls.

The after-run reviewers for 471 and 388 receive no reference-page images because
the dataset marks them unanswerable. Their trace agreement is not independent
visual verification. Direct original-page inspection already recorded in the
previous audits supports the absence conclusions: manual page 19 and strategic
plan final physical page 17. The runtime's 388 image receipt binds the full last
page to `image_2`; it does not reuse the governor name on the cover.

## Follow-up and causal limits

The failed attempt is retained. Follow-up corrects accounting sign handling
independently of separator notation and recognizes common `000s` unit spelling.
When an output retains the identical explicitly scaled source unit, application
normalization can resolve default multipliers from that unit without converting
its value. Contradictory nondefault scales and incompatible conversions remain
invalid. These changes require no extra model call or document-specific rule.

The user authorized rechecking only the two remaining financial questions in the
[separate pair](../adaptive-numeric-pair-20261019/REPORT.md). No other benchmark
questions are included. This targeted run cannot establish that previously
successful questions have no regressions. Routing, inventory closure, visual
conditions and merged-table counting remain separate open issues.

Preflight before this four-row attempt: 250 adaptive tests, 2,180 backend tests
passed, four optional skips and five deselections; Ruff and mypy passed. Raw
results, frozen selection, captures, spans and renders remain local and ignored.
