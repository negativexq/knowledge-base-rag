# Gold-evidence loss audit — v2 baseline, 40/14

Run: `baseline-retrieval-k40` (500/50-word chunks, candidate_k 40, top_n 14, 12k
evidence budget, no generation). 100 answerable questions: 20 had the gold in the
evidence (reported as generation losses, since no model ran); the losses before that
are below.

## 1. Scorer: numeric gold visibility read only the first number (fixed)

`gold_visible` reused answer scoring, which since PR #35 reads the first number an
answer states. Applied to a page, it checked only the page's first number, so a gold
standing in a table ("TOTAL EQUITY | 18,078") counted as missing. 10 of the 23
`not_in_page_text` losses were scorer errors: 1013, 1019, 1022, 1025, 1026, 1028,
1076, 1078, 1081, 1082. Numeric golds are now
looked up exactly among all of the text's numbers. Every gold-in-text and loss-stage
figure reported since PR #35 undercounts numeric visibility; runs must be redone to
correct them (evidence text is not stored in results).

## 2. Retrieval: questions assume their document, the run searched all 13

MMLongBench is single-document QA: each question comes with its PDF and says "the
document", "the first page". The runner searched the whole collection. All 6 Hit@14
misses (385, 387, 393, 663, 829, 1084) have most candidates from other PDFs; the top-1
chunk is from another PDF for 21 of 120 questions (8 of the 20 unanswerable ones). The
benchmark protocol is document-scoped retrieval; production `search()` already takes a
`source_ids` filter (AND-ed with the ACL) but `search_fn` and the chat API do not
expose it.

## 3. Parser: two text-layer losses

- 387: the cover page's text layer reads "Florida Department of Health … Rick Scott
  GOVERNOR … Celeste Philip, MD"; the parser took the page for a table and kept only
  its first row (98 chars of 24 words).
- 364: words are glued where spans meet ("State Bank ofTravancore", "Union Bankof
  India"), so names do not match.

## 4. Answers that must be computed (not in any text)

206, 216, 219, 225, 227 (survey counts = share × sample), 373, 380 (year-over-year
differences), 1014–1017, 1084, 1086 (10-K derived figures: long-term liabilities,
EBITDA, debt, ratios, invested capital; 1084 is also a cross-document miss), 740 (dates reformatted to YYYY-MM-DD). These
need the derived-answer path, not retrieval.

## 5. Format strictness

368: the plant addresses are on the page ("V.K.K. Menon Road (Sahar Road), Chakala…",
"Guldhar … Delhi- Meerut Road") but differ from the gold in punctuation and case.

## 6. Unmeasured

All 48 unmeasured questions are small-number golds (<100), mostly percentages
("21%", "92%"). A literal "N%" lookup would make most of them measurable.

## 7. Assembly

524: pages 15 and 19 are candidates but rank below the 14 anchors; the evidence filled
with the same PDF's pages 1–10.
