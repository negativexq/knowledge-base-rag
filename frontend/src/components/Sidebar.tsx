import {
  BarChart3,
  Database,
  LayoutDashboard,
  RefreshCw,
  Settings,
  Sparkles,
  Waypoints,
} from "lucide-react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"

const PRIMARY_NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/playground", label: "Playground", icon: Sparkles },
  { to: "/knowledge", label: "Knowledge", icon: Database },
  { to: "/sync-runs", label: "Sync Runs", icon: RefreshCw },
  { to: "/evaluations", label: "Evaluations", icon: BarChart3 },
  { to: "/traces", label: "Traces", icon: Waypoints },
]

export function Sidebar() {
  return (
    <nav className="flex h-full w-56 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-4">
      <div className="flex flex-col gap-0.5">
        {PRIMARY_NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
                isActive
                  ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)]"
                  : "text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
              )
            }
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-0.5 border-t border-[var(--color-border)] pt-3">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
              isActive
                ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)]"
                : "text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
            )
          }
        >
          <Settings className="h-4 w-4" strokeWidth={1.75} />
          Settings
        </NavLink>
      </div>
    </nav>
  )
}
