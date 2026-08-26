import { ArrowDown, ShieldCheck } from "lucide-react"

import type { RetrievalReportPayload } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import type { Identity } from "@/api/types"

export function SecurityInspector({
  report,
  identity,
}: {
  report: RetrievalReportPayload | null
  identity: Identity | undefined
}) {
  if (!report) {
    return (
      <p className="text-xs text-[var(--color-muted-foreground)]">
        Ask a question to see the authorization context for that retrieval.
      </p>
    )
  }

  const auth = report.authorization
  const mode = report.security.security_validation_mode
  const modeLabel = mode === "strict" ? "Strict" : mode === "fast" ? "Fast" : mode ?? "—"
  const releasePolicy =
    mode === "strict"
      ? "Validate before release"
      : mode === "fast"
        ? "Post-stream validation"
        : "—"

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-foreground)]">
          <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-success)]" />
          Authorization
        </div>
        <div className="mt-2 grid grid-cols-2 gap-y-1.5 text-xs">
          <span className="text-[var(--color-muted-foreground)]">Tenant ACL</span>
          <Badge variant={auth.acl_applied ? "success" : "warning"} className="w-fit">
            {auth.acl_applied ? "Applied" : "Not applied (system context)"}
          </Badge>
          <span className="text-[var(--color-muted-foreground)]">Tenant</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {auth.tenant_id ?? "—"}
          </span>
          <span className="text-[var(--color-muted-foreground)]">Role</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {identity?.roles.join(", ") ?? "—"}
          </span>
          <span className="text-[var(--color-muted-foreground)]">Retrieval context</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {auth.is_system_context ? "system (privileged)" : "authenticated user"}
          </span>
          <span className="text-[var(--color-muted-foreground)]">User filters applied</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {auth.user_filters_applied ? "yes" : "no"}
          </span>
        </div>
      </div>

      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
        <div className="mb-2 text-xs font-medium text-[var(--color-foreground)]">
          Untrusted RAG context
        </div>
        <div className="grid grid-cols-2 gap-y-1.5 text-xs">
          <span className="text-[var(--color-muted-foreground)]">Context boundary</span>
          <Badge variant={report.security.untrusted_context_enabled ? "success" : "warning"} className="w-fit">
            {report.security.untrusted_context_enabled ? "Isolated" : "Not enabled"}
          </Badge>
          <span className="text-[var(--color-muted-foreground)]">Prompt policy</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {report.security.prompt_policy_version ?? "—"}
          </span>
          <span className="text-[var(--color-muted-foreground)]">Output validation</span>
          <span className="font-technical text-[var(--color-foreground)]">
            {modeLabel}
            {report.security.output_policy_passed === null
              ? " · not yet measured"
              : report.security.output_policy_passed
                ? " · passed"
                : " · failed"}
          </span>
          <span className="text-[var(--color-muted-foreground)]">Release policy</span>
          <span className="font-technical text-[var(--color-foreground)]">{releasePolicy}</span>
        </div>
        {report.security.output_policy_violations.length > 0 && (
          <p className="mt-2 text-[11px] text-[var(--color-error)]">
            Violations: {report.security.output_policy_violations.join(", ")}
          </p>
        )}
      </div>

      <div>
        <p className="mb-2 text-xs font-medium text-[var(--color-foreground)]">Enforcement flow</p>
        <div className="flex flex-col items-center gap-1 text-xs">
          {["UserContext", "mandatory ACL filter", "Qdrant", "authorized candidates only"].map(
            (step, i, arr) => (
              <div key={step} className="flex flex-col items-center gap-1">
                <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 font-technical text-[var(--color-foreground)]">
                  {step}
                </div>
                {i < arr.length - 1 && (
                  <ArrowDown className="h-3 w-3 text-[var(--color-subtle-foreground)]" />
                )}
              </div>
            ),
          )}
        </div>
      </div>

      <p className="text-[11px] leading-snug text-[var(--color-subtle-foreground)]">
        The tenant filter above was applied to the Qdrant query itself, before fusion or
        reranking — a candidate outside {auth.tenant_id ?? "this tenant"} could not have entered
        this response's candidate set.
      </p>
    </div>
  )
}
