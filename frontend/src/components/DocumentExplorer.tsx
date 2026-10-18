import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { DocumentReadRequest, DocumentReference } from "@/api/types"
import { researchApi } from "@/api/research"
import { HighlightedPassage } from "@/components/HighlightedPassage"
import { Button } from "@/components/ui/button"

export function DocumentExplorer({ document, initialPage = 1 }: { document: DocumentReference; initialPage?: number }) {
  const [selection, setSelection] = useState<Omit<DocumentReadRequest, "document">>({ action: "outline" })
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(initialPage)
  const result = useQuery({
    queryKey: ["document-reader", document, selection],
    queryFn: () => researchApi.read({ document, ...selection }),
    staleTime: 0,
  })
  const data = result.data
  return <section aria-label={`Read document ${document.source_id}`} className="mt-3 space-y-3 border-t border-[var(--color-border)] pt-3">
    <p className="break-all text-xs" title={document.document_version}>Source version: {document.document_version.slice(0, 12)}</p>
    {data?.indexed_at && <p className="text-xs text-[var(--color-muted-foreground)]">Last synchronized: {new Date(data.indexed_at).toLocaleString()}</p>}
    {data?.current_version && data.current_version !== document.document_version && <p role="status" className="text-xs text-[var(--color-warning)]">This evidence uses an older document version. Re-run the question for current evidence.</p>}
    {data?.status && data.status !== "active" && <p role="status">This document is no longer active.</p>}
    <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => setSelection({ action: "outline" })}>Headings</Button>
      <form className="flex flex-1 gap-1" onSubmit={(event) => { event.preventDefault(); if (search.trim()) setSelection({ action: "search", query: search.trim() }) }}>
        <input aria-label="Search inside document" maxLength={500} value={search} onChange={(event) => setSearch(event.target.value)} className="min-w-0 flex-1 rounded border border-[var(--color-border)] bg-transparent px-2 text-xs" />
        <Button size="sm" variant="secondary" disabled={!search.trim()}>Search</Button>
      </form>
    </div>
    <form className="flex items-center gap-2 text-xs" onSubmit={(event) => { event.preventDefault(); setSelection({ action: "page", page }) }}>
      <label>Page <input aria-label="Document page" type="number" min={1} max={100000} value={page} onChange={(event) => setPage(Math.max(1, Number(event.target.value)))} className="w-20 rounded border border-[var(--color-border)] bg-transparent p-1" /></label>
      <Button size="sm" variant="secondary">Read page</Button>
    </form>
    {result.isFetching && <p role="status" className="text-xs">Reading document…</p>}
    {result.isError && <p role="alert" className="text-xs">The document could not be read. <button type="button" onClick={() => void result.refetch()}>Retry</button></p>}
    {data?.scan_limited && <p role="status" className="text-xs">Only part of this document was scanned. These results are incomplete.</p>}
    {data?.outline.map((section) => <button type="button" key={section.section_id} className="block w-full rounded p-2 text-left text-xs hover:bg-[var(--color-surface-hover)]" onClick={() => setSelection({ action: "section", section_id: section.section_id })}>{section.title} · {section.chunk_count} passages</button>)}
    {data?.passages.map((passage) => <article key={passage.chunk_id} className="space-y-2 border-l-2 border-[var(--color-border)] pl-3">
      <p className="text-xs text-[var(--color-muted-foreground)]">{passage.heading_path.join(" › ")}{passage.page_number != null && ` · Page ${passage.page_number}`}</p>
      <p className="whitespace-pre-wrap text-sm leading-6"><HighlightedPassage text={passage.text} query={selection.action === "search" ? selection.query ?? "" : ""} prefix={passage.chunk_id} /></p>
      <Button size="sm" variant="ghost" onClick={() => setSelection({ action: "neighbors", chunk_id: passage.chunk_id })}>Read surrounding passages</Button>
    </article>)}
    {result.isSuccess && !data?.outline.length && !data?.passages.length && <p className="text-xs">No accessible passages matched this reading.</p>}
    {data?.has_more && data.next_offset != null && <Button size="sm" variant="secondary" onClick={() => setSelection({ ...selection, offset: data.next_offset! })}>Next results</Button>}
    {(selection.offset ?? 0) > 0 && <Button size="sm" variant="ghost" onClick={() => setSelection({ ...selection, offset: 0 })}>First results</Button>}
    <p className="text-[11px] text-[var(--color-muted-foreground)]">Reading a passage here does not add it to an earlier answer’s verified evidence.</p>
  </section>
}
