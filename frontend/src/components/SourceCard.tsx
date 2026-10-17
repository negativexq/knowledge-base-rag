import { useState } from "react"
import { ChevronRight, FileText } from "lucide-react"

import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { cn, formatScore } from "@/lib/utils"

export function SourceCard({ source, cited, highlighted, technical = false, citedUnits = [], highlightedUnitId = null, cardRef }: {
  source: RetrievedSource
  cited: boolean
  highlighted: boolean
  technical?: boolean
  citedUnits?: SupportUnitRef[]
  highlightedUnitId?: string | null
  cardRef?: (el: HTMLDivElement | null) => void
}) {
  const [expanded, setExpanded] = useState<boolean | null>(null)
  const open = expanded ?? highlighted
  const location = source.heading_path?.length ? source.heading_path.join(" / ") : source.citation_location

  return (
    <div ref={cardRef} className={cn("rounded-lg border transition-colors", highlighted
      ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)]"
      : "border-[var(--color-border)] bg-[var(--color-surface)]")}>
      <button type="button" aria-expanded={open} aria-label={`View source ${source.rank}: ${source.source_id ?? "unknown"}`}
        onClick={() => setExpanded(!open)}
        className="flex w-full items-start gap-3 rounded-lg p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--color-surface-hover)] text-[var(--color-muted-foreground)]"><FileText className="h-4 w-4" strokeWidth={1.5} /></span>
        <span className="min-w-0 flex-1">
          <span className="block break-words text-[13px] font-medium">{source.source_id ?? "unknown"}</span>
          <span className="mt-1 block text-[11px] leading-relaxed text-[var(--color-muted-foreground)]">
            {source.page_number != null && `Page ${source.page_number} · `}{location || source.source_type}
            {(source.section_labels?.length ?? 0) > 1 && <span className="ml-2" title={source.section_labels!.join(" · ")}>+{source.section_labels!.length - 1} more {source.section_labels!.length === 2 ? "section" : "sections"}</span>}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 pt-0.5">
          {cited && <Badge variant="accent">cited</Badge>}
          <span className="font-technical text-[11px] text-[var(--color-subtle-foreground)]">{source.rank}</span>
          <ChevronRight className={cn("h-3.5 w-3.5 text-[var(--color-subtle-foreground)] transition-transform", open && "rotate-90")} />
        </span>
      </button>
      {open && <div className="border-t border-[var(--color-border)] px-4 pb-4 pt-3">
        {citedUnits.length > 0 && <div className="flex flex-col gap-3">
          {citedUnits.map((unit) => (
            <div key={unit.support_id} role="note" data-support-id={unit.support_id} aria-label={`Cited passage ${unit.support_id}`} data-highlighted={unit.support_id === highlightedUnitId}
              className={cn("border-l-2 pl-3", unit.support_id === highlightedUnitId ? "border-[var(--color-accent)]" : "border-[var(--color-border-strong)]")}>
              <div className="mb-1 text-[11px] font-medium text-[var(--color-muted-foreground)]">{unit.section_label || "Cited passage"}</div>
              <p className="whitespace-pre-wrap text-[13px] leading-6">{unit.text}</p>
              {technical && <div className="mt-1 font-technical text-[11px] text-[var(--color-subtle-foreground)]">{unit.support_id}</div>}
            </div>
          ))}
        </div>}
        <details className="mt-2 text-[var(--color-muted-foreground)]" open={citedUnits.length === 0 || undefined}>
          <summary className="cursor-pointer text-[11px] font-medium">Source excerpt</summary>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6">{source.snippet || "No preview available."}</p>
        </details>
        {technical && <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 border-t border-[var(--color-border)] pt-2 font-technical text-[11px] text-[var(--color-subtle-foreground)]">
          <span>{source.source_type}</span>
          {source.token_count != null && <span>{source.token_count} tokens</span>}
          {source.score != null && <span>ranking score {formatScore(source.score)}</span>}
          {(source.section_labels?.length ?? 0) > 1 && <span>{source.section_labels!.join(" · ")}</span>}
        </div>}
      </div>}
    </div>
  )
}
