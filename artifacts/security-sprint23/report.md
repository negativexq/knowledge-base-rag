# Security Sprint 23: Tenant-Aware Retrieval Boundary — Real Local Verification

Real local run against Docker Qdrant + native Ollama (`nomic-embed-text`, real embeddings — not faked) and the real FastAPI app (`app.main.create_app`), not just unit tests. Two real tenants ingested into one shared Qdrant collection via the unchanged `ingest_connector`, each with a document containing a unique, unmistakable secret phrase.

## 1. Ingestion

| | Files processed |
|---|---|
| tenant-a | 1 |
| tenant-b | 1 |

## 2. Cross-tenant retrieval results (real embeddings, real Qdrant, `app.retrieval.search.search()`)

| Scenario | Found own secret | Leaked other tenant's secret | Tenants in result set |
|---|---|---|---|
| A → A (own query) | ✅ true | — | `{tenant-a}` |
| A → B (attack: A asks for B's exact secret) | n/a (correctly absent) | ❌ **false** | `{tenant-a}` |
| B → B (own query) | ✅ true | — | `{tenant-b}` |
| B → A (attack: B asks for A's exact secret) | n/a (correctly absent) | ❌ **false** | `{tenant-b}` |

Both attack scenarios returned results scoped to the ATTACKER's own tenant only — the target tenant's content never entered the result set, confirmed by inspecting every returned point's real `tenant_id` payload field, not just by absence of the secret string.

## 3. Sparse/lexical leakage

Covered separately by `tests/test_cross_tenant_e2e.py::test_exact_lexical_phrase_from_another_tenant_yields_zero_authorized_matches` — real BM25 (fastembed `Qdrant/bm25`) sparse encoding against a real Qdrant server, querying tenant B's exact unique phrase as tenant A. **0 authorized matches.**

## 4. Citation leakage

Covered by `tests/test_cross_tenant_e2e.py::test_citation_for_another_tenants_content_is_never_emitted` — a fake, deliberately malicious chat provider tries to fabricate a citation tag for tenant B's document while serving tenant A's (already ACL-filtered) search results. `check_grounding` correctly marks it `grounded=False` with the tag in `ungrounded_citations`. Not re-run against a real LLM in this local verification — per the sprint's own guidance, a real model's output is not used as the security oracle; grounding is.

## 5. RBAC / sync authorization (real FastAPI `TestClient`, real tokens)

| Request | Result |
|---|---|
| `POST /sync/filesystem`, no credentials | `401` |
| `POST /sync/filesystem`, tenant-a USER token | `403` |
| `POST /sync/filesystem`, tenant-a OPERATOR token (owns "filesystem") | `200` |
| `POST /sync/filesystem`, tenant-b OPERATOR token (wrong tenant) | `403` |

## 6. `/sources` isolation (real tokens)

| Caller | Response |
|---|---|
| tenant-a USER | `[{"source_type": "filesystem", "document_count": 1, "is_running": false}]` |
| tenant-b USER | `[]` — "filesystem" doesn't even appear |

## 7. Performance sanity (ACL filter overhead)

| | Avg per query (real Ollama embed + real Qdrant hybrid search) |
|---|---|
| With mandatory ACL filter (tenant-scoped) | 41.9 ms |
| Without ACL filter (`RetrievalContext.system()`) | 40.2 ms |

~1.7ms difference (~4%), dominated entirely by the real Ollama embedding call (~40ms) — the Qdrant-side ACL filter itself is not a measurable bottleneck. No case was made to relax the ACL for performance reasons; none was needed.

## 8. Security metrics

| Metric | Value |
|---|---|
| `cross_tenant_leakage_rate` | **0%** (0/2 attack attempts leaked) |
| `unauthorized_citation_rate` | **0%** (0/1 fabricated-citation attempt grounded) |
| `unauthorized_sync_success_rate` | **0%** (0/2 unauthorized attempts succeeded: wrong-role, wrong-tenant) |

All targets (0%) met.

## 9. Full automated coverage

`tests/test_cross_tenant_e2e.py` — 12 tests, all against a REAL Qdrant server: dense-only, sparse-only (real BM25), and hybrid isolation; filter-override attack resistance; reranker input isolation; citation leakage prevention; broad/enumeration-style adversarial queries; repeated-query enumeration attempts; explicit proof that `RetrievalContext.system()` (never reachable from a real request) is the only way to see both tenants.
