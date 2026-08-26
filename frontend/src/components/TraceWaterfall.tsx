import { ExternalLink } from "lucide-react"

import type { TraceDetail } from "@/api/types"
import { EmptyState } from "@/components/EmptyState"
import { formatMs } from "@/lib/utils"

export function TraceWaterfall({ trace }: { trace: TraceDetail }) {
  if (!trace.available || trace.spans.length === 0) {
    return (
      <EmptyState
        title="Trace not indexed yet"
        description="Jaeger ingestion is async — try again in a moment, or open it directly."
      />
    )
  }

  const totalMs = Math.max(...trace.spans.map((s) => s.offset_ms + s.duration_ms))

  return (
    <div className="flex flex-col gap-2">
      {trace.spans.map((span) => {
        const leftPct = (span.offset_ms / totalMs) * 100
        const widthPct = Math.max((span.duration_ms / totalMs) * 100, 0.5)
        return (
          <div key={`${span.name}-${span.offset_ms}`} className="flex items-center gap-3">
            <span className="w-40 shrink-0 truncate text-xs text-[var(--color-foreground)]">
              {span.name}
            </span>
            <div className="relative h-4 flex-1 rounded bg-[var(--color-surface-raised)]">
              <div
                className="absolute h-full rounded bg-[var(--color-accent)]"
                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right font-technical text-xs text-[var(--color-muted-foreground)]">
              {formatMs(span.duration_ms)}
            </span>
          </div>
        )
      })}
      <a
        href={`${trace.jaeger_url}/trace/${trace.trace_id}`}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex w-fit items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"
      >
        <ExternalLink className="h-3 w-3" />
        Open in Jaeger
      </a>
    </div>
  )
}
