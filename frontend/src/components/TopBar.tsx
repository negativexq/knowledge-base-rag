import { useQuery } from "@tanstack/react-query"
import { BookOpen } from "lucide-react"

import { DEV_IDENTITIES, getToken, setToken } from "@/api/auth"
import { healthApi } from "@/api/health"
import { Badge } from "@/components/ui/badge"
import { useIdentity } from "@/hooks/useIdentity"

function HealthDot() {
  const { data, isError } = useQuery({
    queryKey: ["readiness"],
    queryFn: healthApi.readiness,
    refetchInterval: 15_000,
    retry: false,
  })

  const ready = data?.ready === true
  const label = isError ? "Unreachable" : ready ? "Healthy" : "Degraded"
  const color = isError || !ready ? "var(--color-error)" : "var(--color-success)"

  return (
    <div className="flex items-center gap-1.5 text-xs text-[var(--color-muted-foreground)]">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
      {label}
    </div>
  )
}

function DevIdentitySwitcher() {
  const current = getToken()
  return (
    <label className="flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
      <span className="hidden sm:inline">Development identity</span>
      <select
        aria-label="Development identity"
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-2 py-1 text-xs text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        value={current ?? ""}
        onChange={(e) => {
          setToken(e.target.value)
          window.location.reload()
        }}
      >
        <option value="" disabled>
          Select identity…
        </option>
        {DEV_IDENTITIES.map((identity) => (
          <option key={identity.token} value={identity.token}>
            {identity.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function TopBar() {
  const { data: identity } = useIdentity()

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4">
      <div className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-[var(--color-accent)]" strokeWidth={1.75} />
        <span className="text-sm font-semibold text-[var(--color-foreground)]">Knowledge Base</span>
        <span className="text-xs text-[var(--color-subtle-foreground)]">Operations Console</span>
      </div>

      <div className="flex items-center gap-4">
        {identity && (
          <>
            <Badge variant="default" className="font-technical">
              {identity.tenant_id}
            </Badge>
            <Badge variant="accent" className="font-technical">
              {identity.roles.join(", ")}
            </Badge>
          </>
        )}
        <DevIdentitySwitcher />
        <HealthDot />
      </div>
    </header>
  )
}
