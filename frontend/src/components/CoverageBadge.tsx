import { useQuery } from "@tanstack/react-query"
import { Library } from "lucide-react"
import { sourcesApi } from "@/api/sources"
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card"
import { documentCoverage } from "@/lib/coverage"

// Before asking: how many documents the question will search, and anything
// about them that changes what to expect from the answer.
export function CoverageBadge({ sourceIds }: { sourceIds?: string[] }) {
  const documents = useQuery({ queryKey: ["coverage-documents"], queryFn: () => sourcesApi.documents(), staleTime: 60_000 })
  if (!documents.data) return null
  const scoped = sourceIds?.length ? documents.data.filter((doc) => sourceIds.includes(doc.source_id)) : documents.data
  const coverage = documentCoverage(scoped)
  const label = `Searching ${coverage.searchable} ${coverage.searchable === 1 ? "document" : "documents"}`
  return <HoverCard openDelay={150}>
    <HoverCardTrigger asChild>
      <button type="button" aria-label={`${label}${coverage.notes.length ? `, ${coverage.notes.length} notes` : ""}`}
        className="flex items-center gap-1.5 rounded px-1.5 py-1 text-[11px] text-[var(--color-subtle-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
        <Library aria-hidden="true" className="h-3 w-3" />{label}
        {coverage.notes.length > 0 && <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-warning)]" aria-hidden="true" />}
      </button>
    </HoverCardTrigger>
    <HoverCardContent className="w-80 text-xs">
      <p className="font-medium">{label}</p>
      {coverage.notes.length
        ? <ul className="mt-2 list-disc space-y-1 pl-4 text-[var(--color-muted-foreground)]">{coverage.notes.map((note) => <li key={note}>{note}</li>)}</ul>
        : <p className="mt-1 text-[var(--color-muted-foreground)]">All documents are indexed and parsed without warnings.</p>}
    </HoverCardContent>
  </HoverCard>
}
