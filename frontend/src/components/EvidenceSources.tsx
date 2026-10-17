import { useEffect, useRef, useState } from "react"
import { ChevronDown, ChevronUp, Search, X } from "lucide-react"
import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { SourceCard } from "@/components/SourceCard"
import { splitAnswerIntoSegments } from "@/lib/citations"
import { passageMatches } from "@/lib/passageSearch"

export function EvidenceSources({ sources, units, highlightedRank, highlightedUnit, technical, citedRanks, cardRef, onPin, isPinned, answer, supportUnits = [] }: {
  answer?: string
  supportUnits?: SupportUnitRef[]
  sources: RetrievedSource[]
  units: Map<number, SupportUnitRef[]>
  highlightedRank: number | null
  highlightedUnit: string | null
  technical: boolean
  citedRanks?: Set<number>
  cardRef: (rank: number, element: HTMLDivElement | null) => void
  onPin?: (rank: number, supportId: string | null) => void
  isPinned: (rank: number, supportId: string | null) => boolean
}) {
  const segments = answer === undefined ? [] : splitAnswerIntoSegments(answer, sources, supportUnits)
  const citations = new Map<number, { marker: string; context: string }[]>()
  let context = ""
  for (const segment of segments) {
    if (segment.type === "text") { if (segment.text.trim()) context = segment.text.trim(); continue }
    if (!segment.valid || !segment.source) continue
    const rank = segment.source.rank
    const links = citations.get(rank) ?? []
    links.push({ marker: segment.text, context: context.length > 600 ? `…${context.slice(-600)}` : context })
    citations.set(rank, links)
  }
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const container = useRef<HTMLDivElement | null>(null)
  const matches = sources.flatMap((source) => [
    ...(units.get(source.rank) ?? []).flatMap((unit) => passageMatches(unit.text, query, `source-${source.rank}:unit-${unit.support_id}`)),
    ...passageMatches(source.snippet, query, `source-${source.rank}:snippet`),
  ])
  const current = matches.length ? Math.min(active, matches.length - 1) : 0
  const activeId = matches[current]?.id
  useEffect(() => {
    const mark = Array.from(container.current?.querySelectorAll<HTMLElement>("[data-match-id]") ?? []).find((element) => element.dataset.matchId === activeId)
    mark?.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [activeId])
  function next(direction: number) { if (matches.length) setActive((current + direction + matches.length) % matches.length) }

  return <div ref={container}>
    <div className="mb-4 flex flex-wrap items-center gap-1.5">
      <div className="flex min-w-32 flex-1 items-center gap-2 rounded-md border border-[var(--color-border)] px-2.5 focus-within:ring-2 focus-within:ring-[var(--color-accent)]">
        <Search className="h-3.5 w-3.5 shrink-0 text-[var(--color-subtle-foreground)]" />
        <input aria-label="Search source passages" placeholder="Find in passages…" maxLength={200} value={query} onChange={(event) => { setQuery(event.target.value); setActive(0) }}
          onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); next(event.shiftKey ? -1 : 1) }
            if (event.key === "Escape" && query) { event.stopPropagation(); setQuery(""); setActive(0) }
          }} className="h-8 min-w-0 flex-1 bg-transparent text-xs outline-none" />
        {query && <button type="button" aria-label="Clear passage search" onClick={() => { setQuery(""); setActive(0) }}><X className="h-3.5 w-3.5" /></button>}
      </div>
      {query && <>
        <span role="status" className="text-[11px] text-[var(--color-subtle-foreground)]">{matches.length ? current + 1 : 0} of {matches.length}</span>
        <button type="button" aria-label="Previous passage match" disabled={!matches.length} onClick={() => next(-1)} className="rounded p-1.5 hover:bg-[var(--color-surface-hover)] disabled:opacity-40"><ChevronUp className="h-3.5 w-3.5" /></button>
        <button type="button" aria-label="Next passage match" disabled={!matches.length} onClick={() => next(1)} className="rounded p-1.5 hover:bg-[var(--color-surface-hover)] disabled:opacity-40"><ChevronDown className="h-3.5 w-3.5" /></button>
      </>}
    </div>
    <div className="flex flex-col gap-2">{sources.map((source) => <SourceCard key={source.rank} source={source} technical={technical}
      cited={answer !== undefined ? citations.has(source.rank) : (units.get(source.rank)?.length ?? 0) > 0 || Boolean(citedRanks?.has(source.rank))} citationLinks={answer !== undefined ? citations.get(source.rank) ?? [] : undefined} citedUnits={units.get(source.rank)}
      highlighted={highlightedRank === source.rank} highlightedUnitId={highlightedRank === source.rank ? highlightedUnit : null}
      cardRef={(element) => cardRef(source.rank, element)} onPin={onPin ? (supportId) => onPin(source.rank, supportId) : undefined}
      isPinned={(supportId) => isPinned(source.rank, supportId)} searchQuery={query} activeMatchId={activeId} />)}</div>
  </div>
}
