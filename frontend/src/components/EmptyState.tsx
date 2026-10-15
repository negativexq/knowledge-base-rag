import type { LucideIcon } from "lucide-react"
import { Inbox } from "lucide-react"

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
      <span className="mb-1 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] shadow-card">
        <Icon className="h-5 w-5 text-[var(--color-muted-foreground)]" strokeWidth={1.5} />
      </span>
      <p className="text-sm font-medium text-[var(--color-foreground)]">{title}</p>
      {description && (
        <p className="max-w-sm text-xs text-[var(--color-muted-foreground)]">{description}</p>
      )}
      {action}
    </div>
  )
}
