# Evaluation Corpus v2 manual review

Review method: opened all eight long documents after the quality rewrite and
read a deterministic 60-question stratified sample. The sample covers the
available categories, all three splits, both query languages, and both
answerability classes where present. This is a wording/evidence review only;
no embedding, reranking, generation, or judge call was made.

## Long-document review

| Source | Review result |
|---|---|
| `employee-handbook-en.md` | Reads as an internal employee/customer-operations handbook; approval, data, access, secrets, audit, conflict, and incident responsibilities are distinct. |
| `long-policy-tr.md` | Natural Turkish policy prose; plan/channel/region/date boundaries, escalation, retention, communication, and audit procedures are explicit. |
| `support-playbook.md` | Operational Tier 1/Tier 2 flow with intake, tenant verification, severity table, routing, incident handling, evidence, handoff, and closure. Numeric targets defer to `support-escalation`. |
| `enterprise-contract-guide.pdf` | Contract-operations reference with precedence, signed/effective dates, amendments, SLA credits, retention, exceptions, and audit evidence. |
| `product-guide-en.pdf` | Product documentation style; plans, seats, roles, API behavior, pagination, versions, deprecation, sandbox, exports, and enterprise overrides are separated. |
| `regional-returns-eu.pdf` | Jurisdiction-specific compliance-oriented guide with withdrawal clock, exceptions, digital goods, channel/plan interaction, contracts, and evidence. |
| `regional-returns-tr.pdf` | Independent Turkish regional operations guide, not a translation of the EU document; delivery, cayma, personalization, digital content, contract, and records differ. |
| `returns-manual-tr.pdf` | Turkish operator runbook with decision table, evidence checklist, approvals, customer communication, and closure flow. |

All long documents add new rules, constraints, exceptions, procedures, or
evidence. No `Operational record N` / `Operasyon kaydı N` filler remains. PDF
text is selectable and Turkish characters are embedded with a Unicode-capable
font when the builder runs on the local or CI host.

## Query review

The following 60 IDs were read for answer determinism, natural phrasing,
near-miss quality, cross-language naturalness, duplicate leakage, and absence
of evaluator instructions:

```text
acl-00-0, acl-00-1, acl-01-0, acl-01-1, acl-02-0, acl-02-1,
acl-03-0, acl-03-1, acl-04-0, acl-04-1, acl-05-0, acl-05-1,
ambiguous-00-0, ambiguous-00-1, ambiguous-01-0, ambiguous-01-1,
ambiguous-03-0, ambiguous-03-1, ambiguous-05-0, ambiguous-05-1,
ambiguous-06-0, ambiguous-06-1, cross-00-0, cross-00-1, cross-02-0,
cross-02-1, cross-03-0, cross-03-1, cross-04-0, cross-04-1,
cross-06-0, cross-06-1, cross-13-0, cross-13-1,
hard-activation-evidence, hard-allowlist-api, hard-annual-cancel,
hard-api-private, hard-api-public, hard-api-version, hard-citation-date,
hard-closure-unknown, hard-order-channel,
injection-00-0, injection-00-1, injection-01-0, injection-01-1,
injection-02-0, injection-02-1, injection-03-0, injection-03-1,
injection-04-0, injection-04-1, multi-00-0, multi-00-1, multi-01-0,
multi-01-1, multi-02-0, multi-02-1, multi-04-0
```

The review found no language-source hints, tenant-boundary instructions, or
answerability-label language in this sample. ACL questions read as ordinary
workspace/product lookups while authorization remains evaluator metadata.
Injection questions ask about legitimate damaged-item handling; the malicious
text remains in the source fixture rather than being repeated in the query.

Known static limitation: wording review cannot establish semantic retrieval
quality. That remains intentionally deferred to the next benchmark sprint.
