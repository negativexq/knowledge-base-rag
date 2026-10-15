import type { LucideIcon } from "lucide-react"

import { Card } from "@/components/ui/card"

export function MetricCard({
  label,
  value,
  icon: Icon,
  caption,
}: {
  label: string
  value: string | number
  icon?: LucideIcon
  caption?: string
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--color-muted-foreground)]">
          {label}
        </span>
        {Icon && (
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-accent-muted)] text-[var(--color-accent)]">
            <Icon className="h-3.5 w-3.5" />
          </span>
        )}
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight tabular-nums text-[var(--color-foreground)]">
        {value}
      </div>
      {caption && (
        <div className="mt-1 text-xs text-[var(--color-subtle-foreground)]">{caption}</div>
      )}
    </Card>
  )
}
