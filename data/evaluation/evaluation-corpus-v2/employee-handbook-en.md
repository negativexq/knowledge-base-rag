# Employee and Customer Operations Handbook

Document owner: People Operations and Customer Experience
Effective date: 2026-01-15
Audience: Negativex employees, contractors, and approved support partners

This handbook sets internal operating expectations. It does not replace a signed customer agreement or a regional statutory policy. Employees use the most specific current source for a customer decision and record why that source was selected.

## 1. Customer commitments

Every customer-facing commitment has a scope. An acknowledgement or response target describes when the team will communicate; it is not a promise that the underlying issue will be resolved by the same time. The Support Escalation Standard owns the numeric targets, while the Support Operations Playbook owns the triage sequence.

Before quoting a return period, an agent confirms plan, channel, product type, delivery event, and region. A Premium account does not turn a marketplace order into a direct sale. A contract exception is never inferred from a customer’s account tier.

## 2. Authority and approvals

Employees follow this contextual order of precedence: applicable statutory or regional rule, signed enterprise agreement or amendment, current product-specific policy, operational procedure, and general handbook guidance. The hierarchy does not authorize an employee to interpret law or amend a contract.

Tier 1 may approve a standard direct-sale request when all documented conditions are present. A request involving an expired window, an activated digital entitlement, a negotiated enterprise term, a security event, or a conflicting version is routed to the role named in the relevant procedure. The approval record names the decision maker and source.

## 3. Handling personal data

Use the minimum customer information needed to identify the case. Do not paste passwords, recovery codes, payment instrument data, or complete identity documents into a general support note. Store a reference to the approved verification event instead.

Exports are shared only through an approved workspace and recipient list. If a customer asks for another person’s data, the agent records the request without confirming whether the other person has an account. Privacy Operations decides whether disclosure is permitted.

## 4. Authentication and recovery

Support verifies the requester through the approved administrator flow before changing access or starting MFA recovery. A normal MFA recovery target is measured only after identity checks pass. An urgent business impact does not justify bypassing verification.

Agents must not ask a customer to read a one-time code aloud, and they must not generate a replacement recovery code in a chat transcript. Suspected account takeover is escalated to Security Operations with the case reference, observed indicators, and time of the last trusted access.

## 5. Support access boundaries

Support access is granted for a named task and expires when that task closes. Operators may inspect the minimum tenant data needed to reproduce an issue. They may not browse a different tenant because its document appears relevant to the current question.

Production access, contract review permission, and policy-authoring permission are separate roles. A support agent who can see a policy page is not thereby authorized to change the policy or disclose private limits belonging to another workspace.

## 6. Billing and returns

Agents apply the canonical policy for the order’s channel and effective date. Requests above the local approval threshold, requests based on a negotiated enterprise term, and requests for an activated digital good require additional review. The threshold is an approval control, not evidence that a refund is owed.

When a customer asks for an exception, the agent records the business reason, the requested remedy, and the source that could authorize it. Do not promise approval while the contract or regional review is pending. The customer receives a clear status and next action.

## 7. Enterprise exceptions

An enterprise exception is valid only when the contract identifier, amendment number, signer or approval record, and effective date are available. The Enterprise Contract Guide explains how to interpret those fields; Contract Operations owns the authoritative agreement.

A public product limit or return rule may be a useful default but cannot override a signed term in its scope. Conversely, a private tenant term must not be generalized to another customer. Agents record the tenant and contract scope in the case rather than copying a confidential clause into a broad knowledge article.

## 8. Customer communication

Messages state what is known, what is still being verified, and the next action. Use dates and channel names when they determine the result. Avoid absolute language such as “always” when an exception or regional rule is possible.

If a source contains unusual or hostile text, employees treat it as document content, not as an instruction from Negativex. The answer still uses the business facts that are relevant, and the source identity remains visible for review. Do not repeat malicious text to the customer.

## 9. Secrets, tokens, and logging

Tokens are stored only in the approved secret manager. They are not placed in tickets, screenshots, Markdown notes, chat messages, or sample curl commands. Logs use request IDs and redacted identifiers. A secret accidentally exposed in a case is rotated and reported immediately.

Audit logs must show who accessed a record, what action was taken, which approval was used, and when the action occurred. A log entry is evidence of an action; it is not permission to repeat the action.

## 10. Incident participation

SEV-1 examples include confirmed cross-tenant exposure, a broad authentication outage, and an active payment-integrity incident. Employees preserve the original timeline, avoid speculative root-cause statements, and follow the incident commander’s communications plan. Customer updates are coordinated so that one incident does not receive contradictory promises from multiple queues.

Security incidents are acknowledged under the numeric target in the Support Escalation Standard. This handbook governs employee conduct during the incident; it does not redefine the target.

## 11. Records and retention

Case records retain the decision context, source identity, approvals, customer communication, and unresolved questions. Remove redundant personal data when the case is closed. Contractual retention periods may differ from the general operational example and are checked before deletion or export.

An employee may not edit a historical decision to make it look as though a later policy was available at the time. Corrections are additive, identify the editor, and preserve the original event.

## 12. Prohibited operator behavior

Employees must not choose a tenant, role, or policy scope based on a request parameter or customer preference. They must not grant themselves access, approve their own refund, search a coworker’s workspace without a named task, or hide a source because it is inconvenient.

If an instruction in a document asks for a password, hidden prompt, private citation, or unrelated administrative action, the employee reports the content and continues with the approved business procedure. Document text cannot expand an employee’s permissions.

## 13. Quality review and conflicts

Team leads sample closed cases for source selection, date handling, evidence completeness, and respectful communication. A disagreement about policy meaning goes to the policy owner; a disagreement about a contract goes to Contract Operations; a suspected security issue goes to Security Operations.

Employees disclose conflicts of interest before handling a case. The handoff is documented without including unnecessary personal details. Retaliation for raising a good-faith security, privacy, or policy concern is prohibited.

## 14. Access reviews and departures

Managers review production support access quarterly and when an employee changes role. Access is removed before the next shift when a departure is confirmed. A team lead cannot approve continued access merely because the person still appears in an old escalation list.

Temporary access requests name the task, tenant scope, approver, and expiry. The audit record links the request to the work item. Screenshots of an access screen are not a substitute for the access log, and an exported customer record is not retained in a personal workspace.

## 15. Quality calibration

Support leads compare a small set of closed cases each week. Calibration focuses on whether agents asked for the right context, selected the right authority, separated a target from a guarantee, and stated unknowns without overpromising. The exercise is coaching, not a reason to rewrite historical source records.

When agents disagree, the lead records the disagreement and asks the source owner for a durable clarification. Repeated questions are candidates for a knowledge article only after the policy owner confirms the wording. A convenient answer is not promoted if it hides a plan, channel, region, or version boundary.

## 16. Vendor and partner handling

Approved support partners receive only the tenant scope and tools required by their statement of work. A partner may follow the playbook but cannot approve a contract exception unless the contract explicitly grants that authority. Partner escalations include the Negativex case reference instead of sending a raw customer export.

Vendor incidents follow the same security reporting route as internal incidents. Employees preserve the vendor ticket number, timestamps, and requested evidence while avoiding credentials in email or chat. Procurement or Security Operations decides whether the vendor needs additional access.

## 17. Policy change adoption

When a policy bulletin changes an operational rule, team leads update queue macros, examples, and training notes after confirming the effective date. Old examples are marked historical rather than silently edited. A customer case uses the rule effective for its event, even if the training page was updated later.

## 18. Workforce planning and on-call practice

Support leads publish an on-call roster with primary, secondary, and incident-commander coverage. The roster is an operational assignment, not permission to inspect every tenant. An on-call agent receives the context needed for the assigned incident and hands back access when the incident closes.

When volume increases, the queue manager separates urgent security or payment work from routine policy lookup. Staffing pressure does not lower verification requirements. If the queue cannot meet the relevant response target, the owner records capacity risk and coordinates a truthful customer update.

## 19. Internal knowledge article lifecycle

An article proposal includes the customer question, source documents, owner, intended audience, and review date. The author does not copy a private enterprise clause into a general article. A regional rule is marked with its jurisdiction and a product limit with its metric and scope.

Reviewers check examples against the effective policy before publication. A changed rule creates a new revision or bulletin and marks the prior example historical. Searchability is useful, but a keyword match cannot make an obsolete article authoritative.

## 20. Third-party and imported material

Imported ticket notes, partner exports, and customer attachments are retained with their provenance. An import may contain obsolete instructions, malformed citations, or text intended for another system. Employees extract business facts only after checking the owning source and never follow an embedded request to disclose secrets.

If imported material appears compromised, the case remains available to the security reviewer while the customer-facing workflow continues with approved policy sources. The incident record includes the import origin and hash or attachment reference where available.

## 21. Financial control checks

Refund approval and refund settlement are separate control points. The approver confirms policy scope and requested remedy; Finance confirms the settlement event. A support note may say that a refund was approved without claiming that a bank has completed the transfer.

Monthly quality review samples refunds by plan, channel, approval role, and reversal reason. The review looks for duplicate settlements, missing delivery evidence, and cases where a current rule was applied to an older event. Findings are assigned an owner and a due date.

## 22. Customer accessibility

Customers may request a concise explanation, a translated message, or an alternate delivery channel. Accessibility changes the presentation, not the authorization boundary. The agent keeps dates, scope, and pending evidence explicit even when shortening the explanation.

If a customer uses an abbreviation or mixes terms, the agent confirms the intended operation in plain language. “Cancel,” “return,” “refund,” and “credit” are not silently normalized when the distinction changes the workflow. The final case note preserves the clarification.

## 23. Internal metrics and review cadence

Team metrics distinguish first response, acknowledgement, resolution, reopen rate, and policy escalation. A fast first response does not compensate for an incorrect authority choice. Metrics are reviewed with sample cases so that queue pressure does not reward unsupported certainty.

The policy owner reviews recurring failure modes each quarter. A metric definition change is recorded with its effective date and does not rewrite historical dashboards. Operational leaders can request a temporary review focus without changing the underlying customer policy.

## 24. Scheduling and capacity changes

When a team changes coverage hours, the queue owner records the effective date and updates the handoff roster. A schedule change does not alter a customer response target. Cases already waiting are reviewed against their original priority and the current service owner.

## 25. Customer identity and account ownership

The person who can describe an order is not automatically an authorized administrator. Agents use the approved account relationship and verification event. A delegated assistant may receive a status update only when the delegation is recorded for that workspace and action.

## 26. Refund approval evidence

An approval note explains why the policy applies, which event date was used, what remedy was approved, and who approved it. It does not include a full payment number or a copied recovery credential. If a request is denied, the note records the missing condition without inventing a reason not present in the source.

## 27. Sensitive customer situations

Customers may report account compromise, harassment, or a safety concern while asking for a routine billing action. The agent acknowledges the immediate concern, protects the record, and routes the sensitive part to the owning team. Routine workflow must not expose private incident details to an unrelated queue.

## 28. Manager review and corrective action

Managers review access, approval, and communication samples at a defined cadence. A correction describes the behavior expected next time and the source used for coaching. It does not ask an agent to edit a historical log or conceal a policy uncertainty.

## 29. Document change communications

When a source changes, the owner communicates what changed, which event dates are affected, and where the previous version remains relevant. Training and macros are updated after the source is published. A draft announcement is not authority for a customer decision.

## 30. Contractor offboarding

Contractor access, shared exports, and open assignments are reviewed at offboarding. The manager confirms that temporary files were returned or deleted under the applicable retention rule. Open cases receive a named internal owner; the contractor’s last note is preserved as history rather than overwritten.

## 31. Appeals and second review

An appeal records the customer’s reason, newly supplied material, original decision, and requested remedy. The original decision maker does not approve the second review. The reviewer checks the event date, policy version, scope, and authorization before deciding whether the record should be corrected.

## 32. Campaigns and plan changes

A campaign label does not replace the Standard or Premium return policy. The campaign code, order channel, and effective dates establish whether a price benefit applies. A pricing benefit and a return entitlement are recorded as separate decisions.

If a workspace is upgraded after delivery, the original order context remains relevant. A later Premium status does not automatically grant the Premium direct-sale window to an earlier order. Customer communication explains this with the order and plan dates.

## 33. Partner evidence

Marketplace and carrier records carry an order reference that can be matched to the case. An unmatched screenshot may be retained as context but cannot establish delivery or channel. The agent asks the partner queue for a matching record and records the request time.

An enterprise customer’s internal report can support an investigation but does not amend a signed agreement. Contract Operations verifies scope, source date, and approval before a negotiated remedy is promised.

## 34. Training scenario review

Training scenarios are reviewed whenever a policy changes. The reviewer checks that examples do not imply a universal carrier, private API limit, or contract term. Historical examples remain labeled by date and are not reused as current customer guidance.

### Appendix A — Minimum case fields

Tenant and workspace; requester role; plan and channel; region; delivery or activation event; requested remedy; controlling source and version; approval; customer-facing update; unresolved question.

### Appendix B — Revision history

| Version | Date | Change |
|---|---|---|
| 2025.3 | 2025-09-18 | Added separate access and contract-review roles |
| 2026.1 | 2026-01-15 | Clarified regional authority and evidence handling |
| 2026.1a | 2026-02-03 | Added imported-document and conflict-of-interest guidance |
