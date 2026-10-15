import { FileText } from "lucide-react"

import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { cn, formatScore } from "@/lib/utils"

export function SourceCard({
  source,
  cited,
  highlighted,
  citedUnits = [],
  highlightedUnitId = null,
  cardRef,
}: {
  source: RetrievedSource
  cited: boolean
  highlighted: boolean
  // Support units of this source that the answer cites, each with its own
  // section; one source card can span several sections of a document.
  citedUnits?: SupportUnitRef[]
  highlightedUnitId?: string | null
  cardRef?: (el: HTMLDivElement | null) => void
}) {
  const location =
    source.heading_path && source.heading_path.length > 0
      ? source.heading_path.join(" / ")
      : source.citation_location

  const sectionLabels = source.section_labels ?? []

  return (
    <div
      ref={cardRef}
      className={cn(
        "rounded-lg border p-3 transition-colors",
        highlighted
          ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)]"
          : "border-[var(--color-border)] bg-[var(--color-surface-raised)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-foreground)]">
          <FileText className="h-3.5 w-3.5 text-[var(--color-subtle-foreground)]" />
          {source.source_id ?? "unknown"}
        </div>
        <div className="flex items-center gap-1">
          {cited && <Badge variant="accent">cited</Badge>}
          <Badge>#{source.rank}</Badge>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--color-muted-foreground)]">
        <span className="capitalize">{source.source_type}</span>
        {location && <span className="font-technical">{location}</span>}
        {sectionLabels.length > 1 && (
          <span title={sectionLabels.join(" · ")}>
            +{sectionLabels.length - 1} more {sectionLabels.length === 2 ? "section" : "sections"}
          </span>
        )}
        {source.token_count !== null && source.token_count !== undefined && (
          <span className="font-technical">{source.token_count} tokens</span>
        )}
        {source.score !== null && (
          <span className="font-technical text-[var(--color-subtle-foreground)]">
            ranking score {formatScore(source.score)}
          </span>
        )}
      </div>
      {citedUnits.length > 0 && (
        <div className="mt-2 flex flex-col gap-1.5">
          {citedUnits.map((unit) => {
            const active = unit.support_id === highlightedUnitId
            return (
              <div
                key={unit.support_id}
                role="note"
                aria-label={`Cited passage ${unit.support_id}`}
                data-highlighted={active}
                className={cn(
                  "rounded-md border-l-2 px-2 py-1.5",
                  active
                    ? "border-[var(--color-accent)] bg-[var(--color-surface)]"
                    : "border-[var(--color-border)]",
                )}
              >
                <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-[var(--color-muted-foreground)]">
                  <span className="font-technical font-semibold text-[var(--color-accent)]">
                    {unit.support_id}
                  </span>
                  {unit.section_label && <span>{unit.section_label}</span>}
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-[var(--color-foreground)]">{unit.text}</p>
              </div>
            )
          })}
        </div>
      )}
      <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-[var(--color-muted-foreground)]">
        {source.snippet || "No preview available."}
      </p>
    </div>
  )
}
