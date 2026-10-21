# Answer coverage audit: row 831

21 October 2026. Runtime audited at main commit `5c65e53`. Read-only investigation;
no runtime changes, paid model calls, benchmark reruns or score changes.

## Finding

The historical answer is supported but materially incomplete. Retrieval supplied
the missing tasks in the exact source unit shown to the answerer. The first
observable omission occurs in answer generation. The scope contract validates
emitted claims and their question restrictions, but does not independently record
whether the requested collection has materially omitted members.

This is distinct from a wrong color, wrong object or unsupported number. A partial
answer can satisfy entity, period and subject bindings while omitting other
activities under the same requested heading and period.

## Trace and original source

Question: how to prepare for Tomorrow's Workplace Skills for Quarter 3.
The recorded three-call run used need planner, answerer and scope validator;
25.65 in-run seconds. No tools, extraction, arithmetic, budget stop or retry.

| Stage | Recorded observation |
| --- | --- |
| Need planning | Retains the subject, preparation-guidance request and Quarter 3 restriction; operation is lookup. No inventory of requested activities is established. |
| Visible evidence | E2.S1 is selected for the answerer. Its text includes motivation interview/team activities, supplier research, local-business research and product analysis. Although 47 other support units are omitted from context, the missing tasks remain in the selected unit itself. |
| Answer generation | Summarizes the motivation interview and adjacent team exercise, adding its own narrower framing, “interview activity”. Does not mention the three other requested-heading activities. |
| Scope review | Returns supported, citing the interview/team passage and Quarter 3 context. No failure codes. It establishes support for what was written, without identifying omitted activities. |
| Release | Publishes the partial answer normally. No technical terminal error explains the omission. |

The original PDF's physical page 7 starts Quarter 3 and includes Unit 9's
Preparing for Tomorrow's Workplace Skills interview: reflect on motivation and
interview friends/classmates. A team exercise is a separate neighboring heading.
Physical page 8 includes three additional occurrences of the requested heading:

- Research supplier requirements at several companies and create a sourced
  comparison chart.
- Choose a local small business, interview its owners, identify critical resources
  and consider supply-chain disruption responses.
- Choose a frequently used product, analyze its target market and marketing
  strategy, and consider adaptation to other market segments.

Physical page 16 repeats these activities in the Quarter 3 column of the summary
table; Quarter 4 is a separate column. Complete page renders 7, 8 and 16 were
inspected, and page 9 text confirms the later Quarter 4 transition. System Poppler
was unavailable, so the existing PyMuPDF renderer was used. Renders remain ignored.

The benchmark label lists the latter three task openings, but this is not a reason
to forbid the source-supported interview from a broad answer. A useful response
can summarize the four matching activity groups and label adjacent team work as
supplementary if included. It need not reproduce every instruction, quiz, learning
outcome or neighboring Quarter 4 activity. No gold count should become runtime policy.

## Current-code admission replay

Reused the selected source text, historical answer and original planner constraints
with the current `AdaptiveSession.verify` path. The scope response was explicitly
mocked: the original supported claim check plus all three current requirement
bindings marked supported with valid source locations. The original incomplete
answer still receives an accepting release receipt with no failure codes.

This proves the admission contract has no separate omission check. It does not
predict that a fresh current-model run would necessarily repeat the historical
omission. No live score is inferred from a mock judgment.

## Minimal correction boundary

Use the existing scope call to judge two independent properties: support for the
emitted claims, and material coverage of the requested task/collection. For a
material omission, return source locations of the missing activity and its
subject/period binding. The application retains the supported answer and requests
only the missing content through the existing repair path, under existing budgets.

Do not make every question enumerate an entire document, require all evidence
needs to produce tool-generated facts, or force extra extraction for ordinary text
answers. A single-value lookup and a broad activity request have different coverage
obligations. A same-source omission should reuse the already visible source, not
trigger retrieval or a freshness requirement. Completeness of the visible window
must also remain distinct from whole-document closure.

First test same-source partial/full answers, a genuine single-activity request,
duplicate activity descriptions, paraphrased summaries, and irrelevant neighboring
periods/headings. Then measure 831 and previously correct prose/list controls
sequentially. Add no extra judge call or reference-answer matching rule.

Row 831 remains unresolved. Historical counts remain 99/120 accepted outcomes,
including two qualified calculations, with 21 unresolved questions.
