import { DocumentExplorer } from "@/components/DocumentExplorer"
import { useState } from "react"
import { ChevronRight, FileText, Pin } from "lucide-react"

import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { HighlightedPassage } from "@/components/HighlightedPassage"
import { Badge } from "@/components/ui/badge"
import { cn, formatScore } from "@/lib/utils"

export function SourceCard({ source, cited, highlighted, technical = false, searchQuery = "", activeMatchId, onPin, isPinned = () => false, citationLinks, citedUnits = [], highlightedUnitId = null, cardRef }: {
  citationLinks?: { marker: string; context: string }[]
  source: RetrievedSource
  cited: boolean
  highlighted: boolean
  searchQuery?: string
  activeMatchId?: string
  technical?: boolean
  onPin?: (supportId: string | null) => void
  isPinned?: (supportId: string | null) => boolean
  citedUnits?: SupportUnitRef[]
  highlightedUnitId?: string | null
  cardRef?: (el: HTMLDivElement | null) => void
}) {
  const [reading, setReading] = useState(false)
  const [expanded, setExpanded] = useState<boolean | null>(null)
  const open = Boolean(searchQuery.trim()) || (expanded ?? highlighted)
  const location = source.heading_path?.length ? source.heading_path.join(" / ") : null
  const locationLabel = [source.page_number != null ? `Page ${source.page_number}` : null, location || (source.page_number == null ? source.source_type : null)].filter(Boolean).join(" · ")

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
            {locationLabel}
            {(source.section_labels?.length ?? 0) > 1 && <>{locationLabel && " · "}<span title={source.section_labels!.join(" · ")}>+{source.section_labels!.length - 1} more {source.section_labels!.length === 2 ? "section" : "sections"}</span></>}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 pt-0.5">
          {cited && <Badge variant="accent">cited</Badge>}
          <span className="font-technical text-[11px] text-[var(--color-subtle-foreground)]">{source.rank}</span>
          <ChevronRight className={cn("h-3.5 w-3.5 text-[var(--color-subtle-foreground)] transition-transform", open && "rotate-90")} />
        </span>
      </button>
      {onPin && <div className="flex justify-end px-3 pb-2">
        <button type="button" aria-label={`${isPinned(null) ? "Unpin" : "Pin"} source ${source.rank}`} aria-pressed={isPinned(null)} onClick={() => onPin(null)}
          className="flex min-h-7 items-center gap-1.5 rounded px-2 text-[11px] text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
          <Pin className={cn("h-3 w-3", isPinned(null) && "fill-[var(--color-accent)] text-[var(--color-accent)]")} />{isPinned(null) ? "Pinned" : "Pin source"}
        </button>
      </div>}
      {open && <div className="border-t border-[var(--color-border)] px-4 pb-4 pt-3">
        {citedUnits.length > 0 && <div className="flex flex-col gap-3">
          {citedUnits.map((unit) => (
            <div key={unit.support_id} role="note" data-support-id={unit.support_id} aria-label={`Cited passage ${unit.support_id}`} data-highlighted={unit.support_id === highlightedUnitId}
              className={cn("border-l-2 pl-3", unit.support_id === highlightedUnitId ? "border-[var(--color-accent)]" : "border-[var(--color-border-strong)]")}>
              <div className="mb-1 text-[11px] font-medium text-[var(--color-muted-foreground)]">{unit.section_label || "Cited passage"}</div>
              <p className="whitespace-pre-wrap text-[13px] leading-6"><HighlightedPassage text={unit.text} query={searchQuery} prefix={`source-${source.rank}:unit-${unit.support_id}`} activeId={activeMatchId} /></p>
              {onPin && <button type="button" aria-label={`${isPinned(unit.support_id) ? "Unpin" : "Pin"} passage ${unit.support_id}`} aria-pressed={isPinned(unit.support_id)} onClick={() => onPin(unit.support_id)}
                className="mt-2 flex min-h-7 items-center gap-1.5 rounded px-2 text-[11px] text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
                <Pin className={cn("h-3 w-3", isPinned(unit.support_id) && "fill-[var(--color-accent)] text-[var(--color-accent)]")} />{isPinned(unit.support_id) ? "Pinned" : "Pin passage"}
              </button>}
              {technical && <div className="mt-1 font-technical text-[11px] text-[var(--color-subtle-foreground)]">{unit.support_id}</div>}
            </div>
          ))}
        </div>}
        {citationLinks !== undefined && <section aria-label={`Citation relationship for source ${source.rank}`} className="mt-4 border-t border-[var(--color-border)] pt-3">
          <h3 className="text-xs font-semibold">Citation relationship</h3>
          {citationLinks.length ? <><p className="mt-1 text-[11px] text-[var(--color-muted-foreground)]">Referenced in this answer.</p><div className="mt-2 space-y-3">{citationLinks.map((link, index) => <div key={`${link.marker}:${index}`}><span className="break-all rounded bg-[var(--color-accent-muted)] px-1.5 py-0.5 font-technical text-[11px] text-[var(--color-accent)]">{link.marker}</span>{link.context && <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-[var(--color-border-strong)] pl-3 text-xs leading-6 text-[var(--color-muted-foreground)]">{link.context}</blockquote>}</div>)}</div></> : <p className="mt-2 text-xs leading-5 text-[var(--color-muted-foreground)]">Retrieved for this question; no matching citation in the answer.</p>}
        </section>}
        <details className="mt-2 text-[var(--color-muted-foreground)]" open={Boolean(searchQuery.trim()) || citedUnits.length === 0 || undefined}>
          <summary className="cursor-pointer text-[11px] font-medium">Source excerpt</summary>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6"><HighlightedPassage text={source.snippet || "No preview available."} query={searchQuery} prefix={`source-${source.rank}:snippet`} activeId={activeMatchId} /></p>
        </details>
        {source.document_version && <div className="mt-3 text-xs text-[var(--color-muted-foreground)]">
          <span title={source.document_version}>Evidence version {source.document_version.slice(0, 12)}</span>
          <button type="button" onClick={() => setReading(!reading)} aria-expanded={reading} className="ml-3 rounded px-2 py-1 text-[var(--color-accent)]">{reading ? "Close document reader" : "Read full context"}</button>
        </div>}
        {reading && source.document_version && source.source_id && source.source_type && <DocumentExplorer document={{ source_type: source.source_type, source_id: source.source_id, document_version: source.document_version }} initialPage={source.page_number ?? 1} />}
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
