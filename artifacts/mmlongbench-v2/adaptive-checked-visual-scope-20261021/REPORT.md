# Preserve checked original-image authority in semantic scope review

21 October 2026. Target: 727, from the
[answerable-control measurement](../adaptive-source-dispositions-20261021/normal-ten/REPORT.md).
The original page reports Germanwings 24 and Lufthansa 12; parser text incorrectly
reports Lufthansa 42. The previous run computed the correct difference but two
scope judgments preferred the conflicting parser digits and withheld the answer.

## Change

The existing semantic scope call for exact application-owned arithmetic/count
candidates now receives the **same original, version-bound pages already reviewed
for their inputs**, alongside checked input bindings and the unchanged parser text.
Original image plus independently checked transcription takes precedence for that
input's reading. Parser text remains available as derivative context for semantic
relationships; it is not rewritten to conceal disagreement.

The application verifies source identity, document version, authorization,
visibility and physical page range before reusing each binding. Repeated pages
are deduplicated. Snapshot rendering uses the existing finalization deadline and
tool timeout. Unavailable or stale image bindings cannot gain this authority.

This is an input/provenance change to the existing scope validator, not another
judge, agent, tool loop or model request. Positive semantic approval remains
required for entity, series, period, unit and formula relationships. Arithmetic
and rounding stay application-owned. Ordinary text claims and text-only checked
calculations receive no added images. Retrieval, embedding, parser output, global
budgets and model effort are unchanged.

Operational spans record the number and physical pages of the images supplied to
scope review. Existing request token estimation accounts for image inputs.
The original unmodified answer/evidence payload remains the release fingerprint.

## Offline verification

**2,387 tests passed**, four skipped and five deselected. Ruff passes; mypy passes
163 application files. New regressions construct a real PDF with Lufthansa 12 and
conflicting parser text 42, then verify that semantic review receives the identical
image bytes supplied to the independent input checker. Tests retain rejection of
wrong semantic binding and stale page/version bindings, deduplicate original
pages, and confirm the text path adds no model call or image.

The README change is limited to adding **96/120 (80%)** to its existing agentic
coverage row, as requested; that aggregate includes two qualified calculations.

## Live measurement

Frozen sequential selection: **727, 729, 1079, 507, 728**. This checks the target,
another calculation over the same table, a financial ratio, a direct text lookup,
and a missing-operand negative control. Existing gpt-6-luna fast-path/evidence-needs
profile and hard application limits remain ten main requests, 120,000 tokens and
240 seconds. A 360-second process ceiling includes setup/retrieval/teardown.
All application Python plus the harness are hashed before and after each row.
No paid after-run reviewer is enabled. All five runs completed sequentially with
unchanged source hashes. All four answerable controls publish the expected answer;
the missing-input control safely abstains: **5/5 expected outcomes**.

| Row | Released outcome | Run seconds | SDK requests | Scope-image evidence |
| --- | --- | --- | --- | --- |

Raw JSON, captures, spans, hashes and logs remain local and ignored. Dollar pricing
is not configured, so API dollar cost is unknown. These are reruns of existing
questions; historical coverage totals do not increase merely from a recheck.

| 727 | 12 Tweets = 24 - 12 | 42.16 | 6 | One reviewed original page (16) |
| 729 | 41 Tweets = 24 + 12 + 5 | 39.01 | 6 | One reviewed original page (16) |
| 1079 | 0.627 = 9912 / 15803 | 55.43 | 8 | No image added to scope review |
| 507 | Little Rock | 23.41 | 5 | No image added to scope review |
| 728 | Safe answer not found; Boeing input unavailable | 66.76 | 9 | No image added to scope review |

727 exercises the corrected path directly: the checked application result reaches
one scope call with original page 16; that check accepts it with no failure codes.
It uses **six requests / 42.16 seconds**, compared with ten requests / 104.61 seconds
and no released answer in the preceding control batch. Repeated collection is no
longer needed in this run. This demonstrates the targeted handoff, not a guarantee
of identical latency or all-question accuracy.

729 also exercises the visual path and retains its correct total of 41. The
financial ratio 1079 and prose lookup 507 retain correct answers without image
inputs to their scope calls. 507 uses five requests, including one existing
`SCOPE_NAMED_ENTITY_RELATION_UNGROUNDED` correction; the unchanged text path is not
claimed to have a fixed three-call latency. Missing Boeing input in 728 is still
not substituted with zero or another company's count.

Total main requests: **34**; summed in-run time: **226.77 seconds**. The correction
recovers 727's current regression but adds no new historical success: it was already
in the 79 supported answers. Coverage remains **96/120 (80%) accepted outcomes**,
including two qualified calculations. The earlier 9/10 answerable batch remains
recorded; this is a separate targeted recovery and control measurement.
