# Negativex Product Guide

Document owner: Product Documentation
Version: 2026.1
Audience: Integrators, workspace administrators, and support

## Product scope

This guide describes the public Negativex product surface. Enterprise workspaces may have contract-controlled variations; those terms are verified separately rather than generalized from one tenant.

## Plans and seats

Standard workspaces support 10 seats and Premium workspaces support 25 seats. A seat is an active workspace membership, not an API key or guest link. Enterprise seat limits are read from the signed order form or amendment when one exists.

## Workspace roles

Workspace roles separate billing administration, member management, and read-only reporting. Support may identify the role required for an action but cannot grant a role outside the authenticated administrator workflow. Role changes are logged with actor and timestamp.

## Public API limits

The public API permits 120 requests per minute per API key. Requests may include a maximum page size of 200. Clients should read rate-limit headers, respect Retry-After on 429 responses, and avoid retry storms. These values describe the public surface, not private integrations.

## Authentication

Production API calls use a workspace-scoped key or approved OAuth client. Sandbox keys are prefixed with sk_test_ and cannot access production records. Secret values belong in a secret manager; examples use placeholders and never real credentials.

## Pagination and retries

List endpoints return a cursor when more records remain. Store the cursor with the request context and do not assume page number and cursor are interchangeable. Retry idempotent reads with bounded exponential backoff; mutation retries require an idempotency key.

## API versions

API v3 is current. API v2 remains available for compatibility while clients migrate, but it is deprecated and should not be selected for new integrations. Version is sent in the documented header or endpoint form; a product name alone does not select a version.

## Exports and retention

Workspace exports are permissioned operations and may contain personal data. The export request records requester, scope, format, and delivery destination. General product retention is not a contract guarantee; enterprise retention is checked against the signed term.

## Plan limitations

Premium expands the standard seat allowance but does not automatically change public API rate limits, retention, or marketplace return terms. Each capability page identifies whether a limit is per workspace, key, minute, or object. Similar numbers must not be compared without their metric.

## Sandbox behavior

Sandbox workspaces use synthetic records and separate keys. A successful sandbox response does not prove production permissions or data availability. Test tenants may expose fixtures absent from production, so support records the environment in reproduction notes.

## Enterprise overrides

A negotiated enterprise term can change seats, retention, or an integration limit. Contract Operations verifies the contract identifier, amendment, effective date, and workspace before disclosing the value. The tenant-b private integration page is not a public product limit.

## Deprecation handling

Deprecation notices include affected version, replacement behavior, and a sunset review date. Clients should migrate before sunset rather than wait for an error. Support links the customer version and endpoint to the product notice when opening an escalation.

## Operational errors

A 401 indicates authentication failure; a 403 indicates an authenticated caller lacks permission. A 429 is a rate-limit response and should be handled using headers. A 5xx response is recorded with request ID and timestamp before a retry policy is chosen.

## Reference examples

For a paginated read, send the workspace-scoped credential, a page size no greater than 200, and the returned cursor on the next request. For a write, use the current API version and an idempotency key. Examples explain behavior; they do not grant permission.

## Support references

Related sources include Tenant B Private Integration Limits, Account Security, and the Enterprise Contract Guide. When a customer contract conflicts with a public value, cite the contract authority and retain the public guide as contextual reference.
