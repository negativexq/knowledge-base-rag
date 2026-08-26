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
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
      <Icon className="mb-1 h-8 w-8 text-[var(--color-subtle-foreground)]" strokeWidth={1.5} />
      <p className="text-sm font-medium text-[var(--color-foreground)]">{title}</p>
      {description && (
        <p className="max-w-sm text-xs text-[var(--color-muted-foreground)]">{description}</p>
      )}
      {action}
    </div>
  )
}
