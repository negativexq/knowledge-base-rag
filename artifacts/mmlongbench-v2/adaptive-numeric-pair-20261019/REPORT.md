# Numeric representation follow-up: two financial questions

Frozen sequential recheck on 19 October 2026, branch
`fix/research-evidence-completion`, based on `fd3d5ec` with uncommitted changes.
Only rows 1026 and 1025 were run, in that order, as requested. The preceding
[four-question attempt](../adaptive-numeric-four-20261019/REPORT.md) is retained,
including its failures. All application files and the trace harness were hashed
before the pair and checked again before each question.

GPT-6 Luna, fast path, evidence needs and independent review remained enabled.
Shared limits stayed 10 requests, 120,000 tokens and 240 seconds. Embeddings,
retrieval, indexing, model effort and API retry settings did not change. Gold
answers and reference pages were used only for after-run evaluation.

| Row | Published answer | Source normalization receipt | Main time / requests / tools |
| --- | --- | --- | --- |
| 1026 | **495 millions of dollars** | `(495)` → signed `-495`; source and output unit both million dollars; independently accepted spending magnitude → `495`. | 41.80 s / 6 / 1 |
| 1025 | **1358000 shares** | `(1,358)` → signed `-1358`; thousand shares → shares; independently accepted repurchase magnitude → `1358000`. | 39.20 s / 6 / 1 |

Both quantity records have accepted input/coverage/operation/entity review,
completed execution, retained original display strings, canonical signed values,
explicit output conventions and no diagnostic errors. Finalization publishes both
answers. Neither main run uses an API retry or a diagnostic repair retry.
Independent review confirms both answers against the original PDF's printed
page 29 Stock Repurchase Programs paragraph. Runtime extraction used text from
physical page 39's equity table; the separate paragraph provides independent
support rather than a claim that the runtime inspected that image.

## Shared correction and limits

Accounting parentheses express sign independently of decimal/group separator
notation. Canonical source notation accepts parenthesized plain decimals while
still rejecting grouped commas without an explicit grouped notation. Thousand
unit labels accept `000`, `000s`, `000's` and `000’s`.

When source and output retain the identical explicit unit and both multipliers
are default one, the application derives their common multiplier from that unit;
there is no numerical unit conversion. Contradictory nondefault declarations and
cross-unit scale mismatches still fail. Signed movement and magnitude remain
separate reviewed choices; no unconditional absolute-value conversion was added.
No extra model call or benchmark-specific value/page rule was introduced.

The live 1026 draft exercises accounting parentheses with canonical notation and
default multipliers for an unchanged million-dollar unit. The live 1025 draft uses
`thousand shares`, so the newly supported `000s` spelling is covered by offline
contract tests rather than isolated by this successful live attempt. The prior
1026 checker API error did not recur; this pair does not establish its cause or
elimination.

The first four-row attempt produced clean source-consistent refusals for 471 and
388. Those rows were not rerun after this follow-up. Together these are targeted
recovery outcomes across two frozen revisions, **not an unchanged four-row pass**.
No previously successful live benchmark controls were rerun, so this is not a
zero-regression claim. Textual routing, inventory closure, visual-condition
verification and merged-table counting remain separate open work.

Main time totals 81.00 seconds. Wall time including startup and separate reviews
is 138.57 seconds. Main usage totals 12 requests, 39,380 input tokens, 3,670 output
tokens and 21,166 cached input tokens. Dollar cost is unavailable because price
metadata is not configured; these token totals exclude separate review calls.

Preflight: 257 adaptive tests, including 33 numeric tests; Ruff passed and mypy
passed across 154 application files. Raw results, receipts, captures, frozen
selection, spans and review inputs remain local and ignored.

Post-run backend verification: **2,187 passed, four optional skips and five
deselections**. No runtime edits were made after the frozen pair.
