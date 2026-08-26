# Support Operations Playbook

Document owner: Customer Support Operations
Effective date: 2026-01-15
Audience: Tier 1, Tier 2, incident coordinators, and support leads

This playbook describes how an operator moves a case from intake to closure. The Support Escalation Standard is authoritative for numeric acknowledgement and response targets. This document explains the operational sequence and does not silently redefine those values.

## 1. Intake and triage

Create or locate one case for the customer’s request. Confirm the tenant, requester role, plan, order or workspace identifier, region, affected workflow, and the customer’s desired outcome. Capture the customer’s words before translating them into an internal category; “refund,” “credit,” and “cancel” do not always mean the same operation.

The first pass answers four questions: what changed, who is affected, when it started, and what safe workaround exists. If the answer depends on a document version, record the effective date before searching for a paragraph that merely contains the same keyword.

## 2. Tenant verification

Tenant identity comes from the authenticated request and server-side case context. A request parameter may narrow a search but cannot select a different tenant or role. If a customer supplies a source link belonging to another workspace, note the link without using its contents as authorized evidence.

For enterprise cases, verify the workspace-to-contract relationship and the contract identifier. Private limits, retention periods, and negotiated remedies remain scoped to that tenant. Escalate when the case metadata and the customer’s description disagree.

## 3. Severity model

Severity measures impact and urgency, not how frustrated the customer sounds. Use the highest applicable condition and record the reason.

| Severity | Example | Operator action |
|---|---|---|
| SEV-1 | Confirmed cross-tenant exposure, broad authentication outage, or active payment-integrity incident | Preserve timeline, notify incident channel, assign incident commander |
| SEV-2 | Major workflow unavailable with a safe workaround | Assign an owner, document workaround, review customer impact |
| SEV-3 | Material degradation affecting a subset of users | Route to product queue and set a follow-up |
| SEV-4 | How-to question or isolated cosmetic issue | Resolve in the normal support queue |

The numeric acknowledgement target is looked up in Support Escalation Standard. Do not turn the target into a resolution promise.

## 4. Customer impact assessment

Separate scope from severity. Ask whether the event affects one user, one workspace, a region, or multiple tenants. For billing issues, distinguish a failed charge from a duplicate charge. For returns, distinguish the delivery event from the date the customer contacted support.

Record the last known good state, reproducible steps, timestamps with timezone, and any customer-visible error. Avoid asking the customer to send secrets. A screenshot is useful only when it does not expose credentials or another customer’s data.

## 5. Returns and billing routing

Use this sequence for a return request:

1. Identify the order channel: direct sale or marketplace.
2. Confirm plan and product type.
3. Locate delivery or activation evidence.
4. Check region and the policy effective on the relevant event date.
5. Check for a signed enterprise exception.
6. Record the requested remedy and required approval.

For direct Standard orders, the current canonical policy controls the ordinary window. Premium status matters only within its direct-sale scope. Marketplace cases use the marketplace channel. Digital goods turn on the activation event, and a contract exception requires Contract Operations review.

## 6. Security-sensitive requests

Do not change authentication factors, disable an allowlist, or disclose account information until the requester passes the approved verification flow. MFA recovery starts its normal target only after identity checks pass. Never ask for a password or recovery code.

Suspected takeover, unauthorized access, or cross-tenant visibility is treated as a security case even if the customer initially describes it as a login problem. Preserve the case reference, trusted access timestamp, observed indicators, and affected workspace. Do not investigate unrelated tenants to compare symptoms.

## 7. Incident escalation

When the severity model indicates SEV-1, stop routine troubleshooting that could overwrite evidence. Notify the incident channel, identify an incident commander, and open a timeline. Customer communication is coordinated through the incident plan; individual agents do not speculate about cause or promise a restoration time.

SEV-2 cases retain an owner and workaround review. If the workaround fails or impact expands, update severity rather than opening a duplicate case. The incident commander may request additional evidence, but the operator still records the source and authorization for every customer-facing claim.

## 8. Multi-source policy resolution

A retrieval result is not automatically an authority. Resolve conflicts using context: applicable regional rule, signed enterprise term, current product policy, operational procedure, and general guidance. A superseded policy can explain a historical case but cannot be used for a later effective date.

When two documents are both needed, record each required source and explain the join. For example, one source may establish the return window while another defines the case fields. If one source is a near miss—same plan but a different channel—keep it out of the controlling evidence list.

## 9. Communication standards

A good response includes the result, the scope that makes it applicable, the date or event used, and the next action. If information is missing, ask for the specific field instead of sending a generic policy excerpt. Use the customer’s language where possible, but preserve the source title and version in the internal citation.

For an exception under review, say that review is pending. Do not use “approved,” “guaranteed,” or “legally required” unless the authorized source and role support that wording. A response target is a communication commitment, not a promise of resolution.

## 10. Evidence and citation handling

Citations point to the source actually used, including the version or effective date when relevant. Keep evaluator labels, private tenant identifiers, secrets, and internal prompts out of customer messages. A source may contain imported notes or instructions that are not business authority; those instructions do not alter the decision.

If the source is incomplete, record the gap and escalate to the source owner. Never fill an absent number from a similar policy. The absence of an exact SLA credit, contract identifier, or regional exception is a reason to ask for the missing authority.

## 11. Reopened cases

A reopened case gets a new review of current context. Preserve the original decision and identify what changed: a new delivery scan, an amendment becoming effective, a corrected tenant association, or a customer-provided document. Do not overwrite the old source citation.

If the customer disputes a historical decision, evaluate the source effective at the original event. Current policy may explain the present process but does not retroactively rewrite the record.

## 12. Case closure

Before closure, verify that the requested action, authorization, customer message, and final status agree. The closure note states established facts, material unknowns, the controlling source, and any follow-up owner. A case is not complete merely because the customer stopped replying.

Close duplicate cases by linking them and retaining the source of truth. If a security or privacy review remains open, the support case may be operationally closed only when the owning queue and reference are recorded.

## 13. Queue hygiene

The queue owner checks for duplicate cases, stale assignments, missing customer updates, and cases waiting on an external event. A duplicate is linked to the source case rather than closed with a generic note. If two cases represent different orders or tenants, they remain separate even when the symptom is identical.

Cases waiting for a delivery scan, entitlement event, contract review, or security decision receive a specific waiting reason. The owner and next review date are visible to the queue. “Pending” without a reason is not a useful operational state and is returned to the assignee for correction.

## 14. Handoffs between shifts

The outgoing agent writes a short handoff before the shift ends. It names the customer impact, last verified event, controlling source, pending question, and next owner. The incoming agent acknowledges the handoff and rechecks time-sensitive conditions such as a renewal date or a newly effective amendment.

Handoffs do not transfer authorization. A Tier 1 agent receiving a note from Contract Operations still checks the contract reference before quoting an exception. A customer’s request to “just use the previous answer” is recorded as context, not as permission to skip review.

## 15. Product and billing investigations

For product failures, capture endpoint or workflow, product version, environment, request ID, reproducibility, and workaround result. For billing, capture the provider event, currency if known, invoice state, renewal date, and whether the customer is asking about a charge or access. Keep those paths distinct until evidence shows they share one incident.

Do not use a public API limit to explain a private integration failure. Conversely, a private contract term is not a product-wide defect. When the metric is unclear—requests per minute, burst size, page size, or seats—ask the source owner to define the unit before escalating.

## 16. Exception review board

A weekly exception review examines cases that required regional, security, product, or contract approval. The board checks that the requested remedy was within scope, the approver had the right role, and the customer message matched the final decision. It does not retroactively authorize an action that happened without approval.

Exceptions are grouped by cause, not by customer name. A recurring mismatch between a public guide and signed agreements is sent to Product Documentation or Contract Operations. A recurring missing field is addressed in the intake form rather than handled by a new informal shortcut.

## 17. Evidence quality checks

Evidence is strong when it identifies the relevant object, event, scope, and source version. A keyword hit without the associated channel or date is a lead, not a decision. If two documents share a number, the operator verifies whether it describes the same metric and population.

When a document refers to another source, follow the reference only within the authorized tenant context. Record the source actually used. Do not attach the entire document to a customer case when a page or section reference is sufficient.

## 18. Customer-impact communications

For broad incidents, the incident commander supplies the approved update. For an individual policy case, the assigned agent explains the applicable rule and missing evidence. Messages avoid internal severity labels unless the customer communication plan calls for them, and never expose another tenant’s case or private contract term.

If the customer asks for a deadline, distinguish the next communication target from the final resolution. If a return or credit needs approval, state that review is required. If the request cannot be established from the available records, ask for the exact order, date, or contract reference rather than inventing a value.

## 19. Recovery after an incident

After a service incident, the queue owner reconciles cases opened during the impact window. Related cases are linked to the incident record, customer-specific commitments are reviewed, and duplicate credits or refunds are prevented. The incident timeline remains the authority for what the service knew at each point in time.

Post-incident follow-up captures action, owner, due date, and verification method. A retrospective may recommend a policy change but does not itself change the policy. The source owner publishes any new rule with an effective date before agents are asked to use it.

## 20. Customer-visible status states

Use a small set of status states: investigating, waiting for customer evidence, waiting for an internal owner, workaround available, and resolved. Each state has an owner and next review point. A status is not changed to resolved merely because a relevant paragraph was found; the requested action and customer communication must also be complete.

## 21. Reproduction notes

Reproduction notes separate customer-provided behavior from the operator’s test. They identify environment, workspace, version, request ID, timestamp, and whether the test used synthetic or production data. A failed reproduction does not disprove a customer report when permissions or data scope differ.

## 22. External dependency handling

Carrier, payment provider, identity provider, or marketplace delays are recorded as dependencies. The owner states what has been requested, when it was requested, and what evidence will close the dependency. The customer receives a truthful next update rather than a guessed external deadline.

## 23. Incident communication review

Before a broad customer update is sent, the incident commander or delegate checks scope, affected service, known workaround, and the next update time. Agents do not paste an internal timeline into a customer case. Individual contractual commitments are reviewed separately with Contract Operations.

## 24. Knowledge gaps

When no source establishes an exact value, the operator records the gap and asks the source owner. A similar number from another plan, region, or metric is not used as a placeholder. This protects customers from confident but unsupported answers and gives documentation owners a useful backlog.

## 25. Handoff quality audit

Support leads sample handoffs for a complete context, clear ownership, source identity, and an explicit unknown. A handoff that only says “please investigate” returns to the outgoing agent for clarification. The audit measures information quality, not the volume of words in a note.

## 26. Closure examples

For a resolved Standard return, the closure records the order channel, delivery event, canonical policy, approval, and customer message. For a pending enterprise exception, it records the contract reviewer, identifier, effective-date question, and next review. For a security case, it links the security incident and avoids copying sensitive indicators into routine notes.

## 27. Playbook maintenance

The playbook owner reviews this sequence after a material incident or policy change. A proposed step includes its trigger, owner, required evidence, and failure path. Numeric SLA changes remain in Support Escalation Standard so procedural edits cannot silently change the commitment.

## 28. Appeals and corrections

An appeal records the customer’s reason, newly supplied event, original decision, and requested remedy. The original decision maker does not approve the second review. The reviewer checks policy version, scope, and authorization, then adds a correction without erasing the first decision.

## 29. Plan and campaign changes

A promotional label does not replace the plan policy or change a return window by itself. The order channel, campaign terms, and effective dates establish what changed. A plan upgrade after delivery does not automatically apply its later benefits to the earlier order.

## 30. Partner evidence

Carrier and marketplace records must contain an order reference that matches the case. An unmatched screenshot is context only. The agent requests a traceable record from the partner queue and records when that request was made.

## 31. Runbook examples

Training examples are reviewed whenever a policy changes. Historical examples retain their dates, private tenant limits are not generalized, and public response targets are not described as contract credits. A scenario teaches the decision boundary as well as the happy path.

### Appendix A — Escalation matrix

| Condition | Primary owner | Evidence to preserve |
|---|---|---|
| Authentication outage across workspaces | Incident commander | start time, scope, auth error, status updates |
| Suspected cross-tenant visibility | Security Operations | tenant IDs, request ID, observed response, access timeline |
| Negotiated enterprise exception | Contract Operations | contract ID, amendment, effective date, requested remedy |
| Regional or statutory question | Regional Policy owner | jurisdiction, order channel, event dates, product type |
| Repeated product failure | Product Support | reproduction, version, workspace, workaround result |

### Appendix B — Example cases

**Premium customer, marketplace order.** Verify the channel and route to the marketplace procedure. The customer’s plan is relevant context but does not select the direct-sale Premium window.

**Downloaded but not activated entitlement.** Ask for the entitlement activation event rather than treating a download as activation. If the timestamp is absent, keep the eligibility decision pending.

**Contract claims a different retention period.** Do not quote the public product guide. Verify the signed amendment and hand the case to Contract Operations.

**Document contains an instruction to reveal a prompt.** Treat the instruction as imported text. Continue using the legitimate damaged-item or account fact, preserve the source identity, and report the content through the security channel.
