import { BookOpen, PanelLeftClose, PanelLeftOpen } from "lucide-react"
import { NavLink } from "react-router-dom"

import { useIdentity } from "@/hooks/useIdentity"
import { NAV_GROUPS, type NavItem, SETTINGS_ITEM } from "@/lib/nav"
import { cn } from "@/lib/utils"

function SidebarLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      aria-label={item.label}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "group relative flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
          collapsed ? "justify-center px-0" : "justify-center px-0 md:justify-start md:px-2.5",
          isActive
            ? "bg-[var(--color-surface-hover)] text-[var(--color-foreground)]"
            : "text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              aria-hidden="true"
              className="absolute -left-3 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-[var(--color-accent)]"
            />
          )}
          <Icon
            className={cn("h-4 w-4 shrink-0", isActive && "text-[var(--color-accent)]")}
            strokeWidth={1.75}
          />
          {!collapsed && <span className="hidden md:inline">{item.label}</span>}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  const { data: identity } = useIdentity()
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] py-3 transition-[width] duration-200",
        collapsed ? "w-[60px] px-2" : "w-[60px] px-2 md:w-56 md:px-3",
      )}
    >
      <div className={cn("flex h-9 items-center gap-2.5 px-1", collapsed && "justify-center px-0")}>
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-foreground)] shadow-card">
          <BookOpen className="h-4 w-4" strokeWidth={2} />
        </span>
        {!collapsed && (
          <div className="hidden min-w-0 leading-tight md:block">
            <div className="truncate text-sm font-semibold tracking-tight">Knowledge Base</div>
            <div className="truncate text-[11px] text-[var(--color-subtle-foreground)]">
              Research workspace
            </div>
          </div>
        )}
      </div>

      <nav aria-label="Main" className="mt-5 flex flex-1 flex-col gap-4 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-0.5">
            {collapsed ? (
              <div className="mx-auto mb-1 h-px w-6 bg-[var(--color-border)]" aria-hidden="true" />
            ) : (
              <div className="hidden px-2.5 pb-1 text-[10px] md:block font-medium uppercase tracking-wider text-[var(--color-subtle-foreground)]">
                {group.label}
              </div>
            )}
            {group.items.map((item) => (
              <SidebarLink key={item.to} item={item} collapsed={collapsed} />
            ))}
          </div>
        ))}

        <div className="mt-auto flex flex-col gap-0.5">
          <SidebarLink item={SETTINGS_ITEM} collapsed={collapsed} />
        </div>
      </nav>

      <div
        className={cn(
          "mt-3 flex items-center gap-2 border-t border-[var(--color-border)] pt-3",
          collapsed ? "flex-col" : "flex-col md:flex-row md:px-1",
        )}
      >
        {identity && (
          <div
            className={cn("flex min-w-0 items-center gap-2 md:flex-1", collapsed && "flex-none")}
            title={`${identity.user_id} · ${identity.tenant_id}`}
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-muted)] text-xs font-semibold uppercase text-[var(--color-accent)]"
            >
              {identity.user_id.slice(0, 1)}
            </span>
            {!collapsed && (
              <div className="hidden min-w-0 leading-tight md:block">
                <div className="truncate text-xs font-medium">{identity.user_id}</div>
                <div className="truncate font-technical text-[11px] text-[var(--color-subtle-foreground)]">
                  {identity.tenant_id} · {identity.roles.join(", ").toLowerCase()}
                </div>
              </div>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-subtle-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        >
          <ToggleIcon className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </div>
    </aside>
  )
}
