# TechQA Validator Calibration DEBUG V1

## Scope

This is a provider-free DEBUG/dev calibration. It uses the pinned
`basic50-claim-local-validator` historical development cases plus deterministic
synthetic contract fixtures. The consumed corrected HOLDOUT was not read or
used for tuning. No production validator code, prompt, retrieval, embedding,
reranker, generation model, security policy, or BGE decision was changed.

Population: 23 calibration cases; 10 historical validator query IDs
and 15 synthetic fixtures.

## Baseline and sequential candidates

Metrics classify a candidate's direct conflicts against known TRUE_CONFLICT
fixtures as true conflicts and direct conflicts against known
FALSE_POSITIVE fixtures as false positives. Indeterminate outputs remain
indeterminate. `forced_abstain_proxy` counts unresolved/rejected known false
positive cases; no new generation was run.

| Candidate | TP | FP | IND | TP recall | FP delta | forced-abstain proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BASELINE | 6 | 1 | 4 | 0.8571428571428571 | +0 | 4 |
| NUMERIC | 6 | 0 | 2 | 0.8571428571428571 | -1 | 1 |
| VERSION | 6 | 0 | 1 | 0.8571428571428571 | -1 | 0 |
| IDENTIFIER_NEGATIVE | 7 | 0 | 1 | 1.0 | -1 | 0 |
| SEGMENTATION | 7 | 0 | 1 | 1.0 | -1 | 0 |

Known true-conflict recall is measured on
7 labeled true-conflict
fixtures; historical dev cases contain no labeled true conflict. Determinate
precision and false-positive rate are reported in each candidate JSON and
exclude indeterminate cases.

Candidate order was fixed before evaluation: Numeric → Version →
Identifier/Negative → Segmentation. Each candidate is evaluated cumulatively
against the same population, with no semantic end-to-end score.

False-positive fixture coverage: {'historical claim-local fixture': 4, 'numeric canonicalization': 2, 'version normalization': 2, 'identifier/negative handling': 2, 'support segmentation': 1}.

## Decision

Selected candidate: **IDENTIFIER_NEGATIVE**

Status: **VALIDATOR_DEBUG_CANDIDATE_SELECTED**

Selection is a DEBUG calibration result only. It is not production
promotion. A selected candidate requires a new independent evaluation
population and a separate preregistered validation task before any default
change.

## Safety and next work

Existing positive/negative controls passed and no security regression was
introduced by these in-memory candidates. No broad semantic entailment or
global evidence search was added. The next development step, if the selected
candidate is retained, is to freeze it and validate it on a fresh population;
the consumed HOLDOUT cannot be reused as confirmation.
