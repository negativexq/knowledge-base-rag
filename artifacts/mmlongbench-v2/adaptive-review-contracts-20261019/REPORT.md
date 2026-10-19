# Reviewer target contracts and separate diagnostic/source repair slots

## Outcome

**0/2 published answers.** Both frozen targeted questions remained unanswered. The failed attempts remain retained; neither review approval of an abstention nor clean output validation counts as answering an answerable question.

| Row | Published output | Seconds | Main model calls | Tools | App retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 372 | I could not obtain enough evidence to answer this question. | 88.96 | 9 | 2 | 1 |
| 385 | I could not obtain enough evidence to answer this question. | 39.21 | 7 | 2 | 0 |

## What the traces establish

**372:** The reviewer contract now exposes item/operation targets for lists, rather than operands. The model nevertheless used index=null for an item; one diagnostic correction supplied index=0. The independent source-repair slot remained available, so collection continued to a second original-source view. It chose physical pages 8 and 11: the general director-name roster and the Audit Committee table. The categories needed for the complete answer are on physical page 9, which was not opened. The repair preserved the list goal and did not fabricate missing names.

There was another state-routing defect: the reviewer reported coverage=unknown with a grounded boundary objection and a request for a complete company-wide category roster. Only coverage=incomplete was mapped to inventory completion. Unknown therefore went through ordinary slot correction, retained the original three-item shape, and did not prioritize unseen category evidence. Unknown alone is not permission to widen a result; a source-grounded missing-inventory objection is the required trigger.

The saved source units expose a broad **8–16** page range, plus explicit page 8 and page 11 units. The needed page 9 is inside that already admitted range but is not presented as its own clearly located candidate. A bounded native-PDF page catalog can expose its original headings/footer clues and physical identity without changing embeddings or granting access outside the admitted range.

**385:** No timeout occurred in this recheck. The first source selector returned available=false, so collection did not inspect the strategy-map image. Later source selection treated the question's printed page 2 as physical page 2 and correctly rejected that page's cover/version information as the wrong content. The actual three headings are on physical page 5, printed page 2. This is a separate source-discovery/page-location failure from the preceding 60-second provider/model timeout. The already admitted source metadata includes the physical page 5 strategy-map units; the selector's twelve-paragraph projection did not reliably expose that page's relevance.

## Follow-up, implemented after this batch

- Treat incomplete or unknown coverage with a grounded inventory-boundary/missing-item objection as a missing-coverage search. Preserve the original goal; retain only supported items when unioning, otherwise recheck a replacement inventory.
- Retarget repair candidate ranking to the concrete evidence gap instead of preserving initial retrieval anchors for the same insufficient view.
- Supply a typed native-PDF page catalog: original location hints, document version, physical page, and live support IDs, bounded to admitted ranges and source limits. Printed labels remain clues and are never substituted for physical identity. Catalog clues do not certify an answer; original-page extraction and independent release checks remain required.
- Make item/group/operand indexes non-null and in range; operation objections use a distinct typed branch with a null index. A diagnostic correction and a source repair share the same global hard ceilings.
- Validate newly selected IDs against presented candidates before adding already authorized parent evidence for coverage rechecking. Parent provenance does not need to be rediscovered in a newly narrowed candidate projection.

These follow-ups are **not included** in the results above. The next pair has a separate frozen selection and report.

## Controls, validation and usage

Both questions ran once, sequentially, with gpt-6-luna, fast path, evidence-needs planning and separate after-run review. The ten-request/120,000-token/240-second ceilings, effort settings, index, embedding, initial retrieval and reranker configuration stayed unchanged. Main generation saw neither reference answers nor benchmark reference pages. Runtime code was frozen and unchanged during both requests.

Before execution: **2,138 backend tests passed**, four optional skips, five deselected; **208 adaptive tests passed**; Ruff and mypy were clean. These are source-scoped diagnostic rechecks, not an open-corpus score or a full benchmark.

Main usage: **16 calls**, **128.17 seconds**, **60,698 input tokens**, **7,815 output tokens**, **4 tool attempts**, **1 application retries**. Diagnostic review usage is stored separately. Prices are unset, so dollar cost is unavailable.

Historical distinct-question counts remain 30 tried, 27 published source-correct answers, one correct refusal, and two never-successfully-answered rows. The current visual-list failures remain visible alongside its historical success. Only this English summary is intended for Git; raw results, spans, profiles and model captures stay local and ignored.
