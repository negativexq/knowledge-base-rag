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
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--color-muted-foreground)]">
          {label}
        </span>
        {Icon && <Icon className="h-3.5 w-3.5 text-[var(--color-subtle-foreground)]" />}
      </div>
      <div className="mt-2 font-technical text-2xl font-semibold text-[var(--color-foreground)]">
        {value}
      </div>
      {caption && (
        <div className="mt-1 text-xs text-[var(--color-subtle-foreground)]">{caption}</div>
      )}
    </Card>
  )
}
