# Test Suite Rationalization

This document records the test-suite audit and the boundary between permanent
regression coverage and historical experiment evidence. It is intentionally
separate from benchmark result artifacts.

## Before

- 1,233 tests collected (`pytest --collect-only -q`), across 159 test files.
- Provider/Ollama tests were not consistently marked, so the default command
  could enter local-provider E2E paths. A full unfiltered run is therefore not
  the deterministic suite.
- The suite included a cluster of TechQA phase, amendment, holdout,
  reranker, and one-off validator artifact assertions.
- The initial working-tree audit found one pre-existing intentional README
  modification and no unexplained untracked files; all subsequent changes are
  listed in this document's cleanup scope.

## Classification

The audit classified tests by protected contract, not by historical filename:

- **PRODUCT_CORE** — API, retrieval, indexing, chunking, generation contracts,
  lifecycle, and configuration behavior.
- **SECURITY** — authentication, tenant isolation, authorization, hidden and
  cross-query support rejection, prompt-injection boundaries, and fail-closed
  behavior.
- **EVAL_FRAMEWORK** — reusable metric, scorer, evidence, artifact-integrity,
  blind-mapping, and evaluation-harness behavior.
- **BUG_REGRESSION** — tests preserving a reproducible defect fix, including
  safety and persistence failures that could invalidate future runs.
- **EXPERIMENT_HISTORICAL** — exact hashes, paths, query populations, frozen
  counts, and procedure checks for completed one-off experiments.
- **PROVIDER_E2E** — tests requiring live Ollama or other external provider
  services.
- **DUPLICATE** — overlapping historical checks that exercised the same generic
  contract with different experiment constants.

Before cleanup, the historical TechQA files were predominantly
**EXPERIMENT_HISTORICAL** or **DUPLICATE**; the general product, security, and
reusable evaluation tests remain the permanent suite.

The resulting logical classification is: product-core and security groups
retained; reusable evaluation-framework and bug-regression groups retained or
consolidated; 62 experiment-historical tests removed; duplicate historical
checks removed rather than re-created under another runner; and 6 provider E2E
tests separated by marker.

## Changes

- Removed 62 tests from 15 files covering completed Development200/Phase 7 and
  TechQA phase, amendment, holdout, reranker, and one-off validator artifacts.
  These were historical constants, exact paths/hashes/counts, or duplicate
  procedure checks; their immutable reports remain the audit record.
  The removed groups were `development200_results`, `final_integrity_audit`,
  `final_v22_smoke36`, `phase7_closure`,
  `pre_development200_measurement_freeze`, `newly_visible_semantic_judging`,
  and the TechQA amendment/phase/holdout/reranker one-off checks.
- Kept generic critical-value, scorer, evidence-state, Top-N slicing, blind
  mapping, write-once, product, and security behavior tests.
- Removed the exact TechQA artifact assertions from mixed reusable files while
  retaining their reusable unit coverage.
- Pinned-TechQA dataset tests still run their full assertions when the optional
  parquet fixture exists and skip explicitly when it is unavailable.
- Marked 6 live Ollama/provider tests as `ollama_e2e` and registered the marker
  in pytest and CI. The deterministic collection is now 1,165 tests; the
  explicit provider collection is 6 tests.
- Added a generic index-validation regression proving that a required source
  missing from the selected index fails closed before evaluation work.

Provider-dependent E2E tests are marked `ollama_e2e` and excluded from the
default deterministic command. They remain available explicitly with:

```bash
pytest -m "not ollama_e2e"
pytest -m "ollama_e2e"
```

The post-cleanup collection was 1,172 tests in total (1,166 deterministic and
6 provider-marked) across 144 test files. Runtime is recorded by the validation
commands used for this change; collection itself remained under ten seconds.

## Validation

- Focused changed-infrastructure tests: 9 passed.
- Deterministic suite: 1,166 collected; 1,165 executed, with 1 optional
  credential-gated Notion test skipped; runtime 36.76 seconds.
- Ruff: passed. Compile/import check: passed. `git diff --check`: passed.
- Secret scan of changed files: no leaks found.
- Ollama E2E: not run; 6 tests were collected separately and deselected from
  the deterministic run.

No deleted test was left unexplained: removals are historical artifact
assertions or duplicate procedure checks, while reusable behavior and security
coverage remain in the permanent suite.

## Coverage deliberately preserved

- tenant ACL and support-ID authorization;
- critical-value and citation validation behavior;
- retrieval, RRF, SectionAware, and API contracts;
- corpus coverage and annotation-mappability logic;
- scorer math and blind/unblind infrastructure;
- immutable raw-byte hashing and write-once artifact helpers;
- regressions for real security and persistence bugs.

## Policy going forward

> Do not add permanent pytest tests solely to validate one experiment
> execution.

> Add a permanent test only when reusable product behavior, reusable
> evaluation infrastructure, security behavior, or a real bug regression is
> being protected.

> Historical experiment results belong in immutable artifacts, not the
> always-running regression suite.
