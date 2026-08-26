# Tenant B Private Integration Limits

Contract owner: Enterprise Platform Operations
Applies to: tenant-b private integration keys
Control: negotiated tenant-specific service term

The tenant-b integration plan permits 600 requests per minute per API key, with a burst of up to 40 requests. Clients should honor the `Retry-After` header on a 429 response and use exponential backoff rather than replaying the whole batch immediately.

These limits are private contract terms. They do not describe the public API and cannot be applied to tenant-a. The contract identifier and effective amendment must be checked before a support agent discloses the limit to another workspace.
