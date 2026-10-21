# Original-image handoff for visual conditions

21 October 2026. Targets: 635 (grey background), 638 (lower figure), 660
(requested port range). Positive controls: 634 (blue background), 637 (upper
figure), 659 (supported port range). See the [source/code audit](../../../docs/adaptive-visual-condition-audit.md).

## Implementation

The existing scope call now receives original pages for exact independently
checked list candidates, as well as arithmetic/count candidates. List answers
remain visible as lists; no arithmetic authority is assigned to label or visual
condition judgments. Changed candidates, unaccepted inputs and stale bindings
do not gain this image authority.

The first six runs exposed another route: generic scoped image extraction can
produce a name list without using the quantity/list collector. This route now
also preserves the original page. The application joins admitted image facts to
their original extraction records, accepted observation indexes, parent support
IDs, source/version/page and active need bindings. It adds the original source
to the candidate's support IDs, validates authorization and page ranges, and
renders the same immutable PDF snapshot. Pages are deduplicated across routes.
Unaccepted drafts are not promoted to facts.

Both application proofs and admitted image transcriptions are labeled generated
in the scope payload. A condition cannot be approved from generated text alone.
The existing scope response can identify a supplied image and record a short
observation of the relevant object/condition; the application checks that the
image belongs to the cited claim. Direct original text remains valid for textual
conditions. This is source binding, not a deterministic color classifier or a
guarantee that every model judgment is correct.

Extraction-coverage context now includes the actual reading method and physical
page, so a rejected image observation is distinguishable from a text-only attempt.
No new model role, judge loop or mandatory request is added. Retrieval, embedding,
effort settings and global budgets remain unchanged. No row IDs, expected answers,
document pages, colors or document-specific conditions enter runtime code.

## Sequential measurement

Existing gpt-6-luna `--fast-path --evidence-needs` profile: ten main requests,
120,000 tokens, 240-second application limit and 360-second process ceiling.
No paid after-run reviewer. All app Python files and the harness were frozen
before each batch and verified unchanged through its completion. Rows ran
sequentially; answers were inspected only after each full batch completed.

| Row | First six-row result | In-run seconds | Requests | Evidence |
| --- | --- | --- | --- | --- |
| 635 | Unnecessary request to provide an already available figure; not accepted as success | 64.65 | 9 | No accepted facts or scope call; generic extraction rejected its proposals |
| 638 | Safe insufficient evidence | 87.76 | 9 | Independent checker rejects Figure 2 at the top as evidence for the requested lower Figure 3 |
| 660 | Safe insufficient evidence | 108.71 | 9 | Scope rejects unsupported range; repeated candidate repair remains inefficient |
| 634 | Correct `["Fact Checker"]` | 71.78 | 9 | Generic image facts bypassed list-page reuse; first scope rejection, then text-only acceptance exposed the remaining handoff gap |
| 637 | Correct count 1 | 54.17 | 5 | Scope receives pages 4–6 and explicitly binds its observation to upper Figure 2 on physical page 5 |
| 659 | Correct Port 1 / P1.1, T2EX | 35.27 | 3 | Ordinary text path remains valid without image inputs |

The generic-fact correction was then measured on the affected pair, again frozen
and sequential:

| Row | Follow-up result | In-run seconds | Requests | Evidence |
| --- | --- | --- | --- | --- |
| 634 | Correct `["Fact Checker"]` | 90.12 | 7 | One scope call receives original physical page 2, cites both transcription and original source, and observes the two light-blue Fact Checker boxes directly; no retry |
| 635 | Safe insufficient evidence | 51.73 | 9 | Source selector rejects the grey condition on the available figure; no invented function list or unnecessary upload request is released |

The final pair passes both expected outcomes. Together with the preceding
count/range controls, the latest observed outcomes are three supported answers
and three safe negatives, with no incorrect answer released. Only 634 directly
exercises the generic-fact image handoff live; the exact list route is covered
offline. The negative 635 run stops at source selection, so it does not prove
that a falsely accepted grey transcription would always be rejected later.

Original source renders were checked independently: Figure 1's function boxes
are blue, pink and green; the complete prompt example belongs to the upper
Figure 2 on printed page 6985; the lower Figure 3 shows QA settings. The port
description binds T2EX to P1.1, not a port in the requested 10–13 range. Combined
with safe live insufficiency, 635/638/660 meet the existing user-approved negative
acceptance criterion. They move from unresolved to correct refusals; this is not
a new runtime whole-document absence certificate.

The six-row batch used 44 requests / 422.34 summed in-run seconds; the pair used
16 / 141.85. Dollar prices are unconfigured, so API dollar cost is unknown. The
634 follow-up uses fewer calls but took longer than its preceding run; no general
latency gain is claimed. Raw results, captures, images, hashes and spans remain
local and ignored.

## Verification and remaining work

**2,392 tests passed**, four skipped and five deselected. Ruff and mypy pass.
Regressions cover original page bytes, exact list matching, retained list text,
independent semantic rejection, generic extraction lineage, generated-only
condition rejection, invalid image/claim references and unchanged text support.

Repeated repair/search after a known mismatch remains inefficient: 660 uses four
scope calls, and 635 still spends nine requests. The first 660 scope output also
omits its required objection; existing validation refuses that malformed receipt.
Neither issue authorizes weakening acceptance. Multi-page inventory closure and
other relationship defects are outside this correction.

There are still 120 distinct questions. Historical outcomes become **79 supported
answers / 2 qualified calculations / 18 correct refusals / 21 unresolved**:
**99/120 (82.5%) accepted outcomes**, including the two qualified calculations.
This is a historical ledger update, not a full current-code rerun of 120 questions.
