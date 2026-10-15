import { useQuery } from "@tanstack/react-query"
import { Moon, Search, Sun } from "lucide-react"
import { useLocation } from "react-router-dom"

import { DEV_IDENTITIES, getToken, setToken } from "@/api/auth"
import { healthApi } from "@/api/health"
import { navItemFor } from "@/lib/nav"
import { themeSwitchLabel, useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"

function HealthPill() {
  const { data, isError } = useQuery({
    queryKey: ["readiness"],
    queryFn: healthApi.readiness,
    refetchInterval: 15_000,
    retry: false,
  })

  const ready = data?.ready === true
  const label = isError ? "Unreachable" : ready ? "Healthy" : "Degraded"
  const ok = ready && !isError

  return (
    <div
      className={cn(
        "flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
        ok
          ? "border-[var(--color-success-muted)] bg-[var(--color-success-muted)] text-[var(--color-success)]"
          : "border-[var(--color-error-muted)] bg-[var(--color-error-muted)] text-[var(--color-error)]",
      )}
    >
      <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-50" />
        )}
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      {label}
    </div>
  )
}

function DevIdentitySwitcher() {
  const current = getToken()
  return (
    <select
      aria-label="Development identity"
      title="Development identity"
      className="h-7 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs text-[var(--color-foreground)] transition-colors hover:border-[var(--color-border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
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
  )
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { pathname } = useLocation()
  const page = navItemFor(pathname)
  const { theme, toggleTheme } = useTheme()
  const ThemeIcon = theme === "dark" ? Sun : Moon

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-4 border-b border-[var(--color-border)] bg-[color-mix(in_oklch,var(--color-background)_80%,transparent)] px-5 backdrop-blur-md">
      <div className="min-w-0 flex-1">
        {page && (
          <div className="flex min-w-0 items-baseline gap-3">
            <h1 className="shrink-0 whitespace-nowrap text-[15px] font-semibold tracking-tight">{page.label}</h1>
            <p className="hidden min-w-0 truncate text-xs text-[var(--color-subtle-foreground)] xl:block">
              {page.description}
            </p>
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={onOpenPalette}
        aria-label="Search or jump to…"
        aria-keyshortcuts={isMac ? "Meta+K" : "Control+K"}
        className="hidden h-8 w-48 shrink items-center whitespace-nowrap lg:w-64 gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-xs text-[var(--color-subtle-foreground)] transition-colors hover:border-[var(--color-border-strong)] hover:text-[var(--color-muted-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] md:flex"
      >
        <Search className="h-3.5 w-3.5" />
        Search or jump to…
        <kbd className="ml-auto rounded border border-[var(--color-border)] px-1.5 font-technical text-[10px]">
          {isMac ? "⌘K" : "Ctrl K"}
        </kbd>
      </button>

      <div className="flex items-center gap-2">
        <DevIdentitySwitcher />
        <HealthPill />
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={themeSwitchLabel(theme)}
          title={themeSwitchLabel(theme)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        >
          <ThemeIcon className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </div>
    </header>
  )
}
