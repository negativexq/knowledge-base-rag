import { AlertTriangle } from "lucide-react"

import { cn } from "@/lib/utils"

export function CitationChip({
  rank,
  supportId,
  valid,
  onClick,
}: {
  rank: number | undefined
  // Set for a support-ID citation ("E1.S4"); shown in place of the rank.
  supportId?: string
  valid: boolean
  onClick: () => void
}) {
  if (!valid) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="mx-0.5 inline-flex items-center gap-0.5 rounded border border-[var(--color-error)]/40 bg-[var(--color-error-muted)] px-1 py-0.5 align-middle text-[10px] font-medium text-[var(--color-error)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        aria-label="Unverified citation"
      >
        <AlertTriangle className="h-2.5 w-2.5" />
        cite
      </button>
    )
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-[var(--color-accent-muted)] px-1 align-middle text-[10px] font-semibold text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-[var(--color-accent-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
      )}
      aria-label={supportId ? `Jump to ${supportId} in source ${rank}` : `Jump to source ${rank}`}
    >
      {supportId ?? rank}
    </button>
  )
}
