# Enterprise Contract Guide

Document owner: Contract Operations
Effective date: 2026-01-15
Audience: Support, account operations, and contract reviewers

## Purpose and records

This guide explains how Negativex operations read enterprise terms. The signed agreement, order form, and amendment remain authoritative. Every exception record includes the contract identifier, account owner, amendment number, signed date, and effective date.

## Order of precedence

For a conflict within an enterprise account, review the signed amendment first, then the master agreement, the order form, and finally the public service policy. Precedence applies only when the documents cover the same customer, service, metric, and time period.

## Effective dates

Signed date and effective date are separate fields. A document may be signed in December and become effective in January. Use the effective date for the service decision and retain the signed date for audit. Missing dates stop the exception workflow.

## Account ownership

The account owner confirms which workspace and product family the term covers. A parent company agreement is not automatically evidence for every subsidiary. Contract Operations records the workspace relationship before allowing a negotiated limit or remedy to be quoted.

## Availability commitment

The example enterprise commitment is 99.95 percent monthly availability. Measurement window, excluded maintenance, and service-credit procedure are separate terms. Do not infer a credit amount from the percentage alone; the signed schedule and calculation record are required.

## Service credits

A service credit is not a refund, damages payment, or support response. Record measured availability, eligible service, incident exclusions, notice date, and the credit tier named by the agreement. An absent tier is escalated rather than filled from a public promise.

## Retention terms

The default example is 180 days, but retention is contract-specific. The effective amendment and data class determine whether the value applies to events, exports, or deleted records. Product documentation describes a default and cannot override a signed retention term.

## Digital goods

A negotiated enterprise term may permit a remedy for an activated digital entitlement where the public Digital Goods Policy normally does not. Retain the entitlement ID, activation timestamp, contract clause, and approval. Enterprise status alone is insufficient.

## Returns and regional terms

An enterprise order may contain a special return period, but the clause must identify the order or product scope. Regional statutory requirements are assessed for the transaction jurisdiction. Contract Operations and the regional policy owner resolve overlap; support does not choose the more generous rule by default.

## Amendment review

For each amendment, record the prior clause, replacement clause, affected service, and transition date. A current amendment can supersede only terms within its scope. Historical cases use the effective term at the relevant event, not the latest document opened by the agent.

## Verification checklist

Before approving an exception, confirm the contract identifier, workspace, account owner, signed date, effective date, amendment number, clause scope, requested remedy, required approver, and customer communication. Store references rather than copying confidential full text into a support case.

## Private integration limits

A private integration limit may differ materially from the public API value. The tenant-b example is maintained on its private limits page and is contract-controlled. It must not be generalized to another tenant or presented as the product-wide rate limit.

## Dispute handling

If an account owner and support agent interpret a clause differently, pause the customer commitment and request Contract Operations review. Record both interpretations, the source documents, and the decision owner. Urgency does not authorize an undocumented amendment.

## Audit evidence

Auditors should be able to reconstruct who verified the contract, which version was effective, which metric was measured, and which customer message followed. Logs must not contain API keys, payment data, or unrelated tenant information.

## Related documents

Related operational sources include the Support Operations Playbook, Digital Goods Policy, Product Guide, and regional return guides. They provide context or procedure; the signed agreement controls a negotiated enterprise term within its scope.
