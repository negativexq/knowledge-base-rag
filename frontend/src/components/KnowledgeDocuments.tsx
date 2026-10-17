import { useEffect, useState, type SetStateAction } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3, Search } from "lucide-react"
import { Popover } from "radix-ui"

import type { DocumentRecord } from "@/api/types"
import { CollectionPicker } from "@/components/CollectionPicker"
import { documentKey, documentReference } from "@/lib/organization"
import { KnowledgeSavedViews } from "@/components/KnowledgeSavedViews"
import { ShareViewButton } from "@/components/ShareViewButton"
import { knowledgeColumns as columns, knowledgeViewQuery, readKnowledgeView, type KnowledgeSort as SortKey, type KnowledgePreferences as Preferences, type KnowledgeView } from "@/lib/knowledgeView"
import { useViewSearch, updateViewQuery } from "@/lib/viewState"
import { EmptyState } from "@/components/EmptyState"
import { StatusBadge } from "@/components/StatusBadge"
import { Badge } from "@/components/ui/badge"
import { qualitySummary } from "@/lib/quality"
import { cn, formatRelativeTime } from "@/lib/utils"

const controlClass = "h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-xs text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"

function readPreferences(key: string): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null")
    if (Array.isArray(value?.columns) && typeof value.compact === "boolean") return {
      columns: value.columns.filter((column: unknown) => columns.some((item) => item.key === column)), compact: value.compact,
    }
  } catch { /* Default presentation when browser storage isn't available. */ }
  return { columns: columns.map((column) => column.key), compact: false }
}

function qualityKey(doc: DocumentRecord): string {
  return !doc.ingestion_quality ? "missing" : doc.ingestion_quality.needs_review ? "review" : "ok"
}

export function KnowledgeDocuments({ documents, onOpen, preferencesKey, organizationScope }: {
  documents: DocumentRecord[]
  onOpen: (document: DocumentRecord) => void
  preferencesKey: string
  organizationScope?: string
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const selectedDocuments = documents.filter((document) => selected.has(documentKey(documentReference(document))))
  const [defaults] = useState(() => readPreferences(preferencesKey))
  const view = readKnowledgeView(useViewSearch(), defaults)
  const { search, status, quality, sort, page, pageSize } = view
  const preferences = { columns: view.columns, compact: view.compact }
  function patch(values: Partial<KnowledgeView>) {
    updateViewQuery(knowledgeViewQuery({ ...readKnowledgeView(window.location.search, defaults), ...values }))
  }
  const setSearch = (search: string) => patch({ search })
  const setStatus = (status: string) => patch({ status })
  const setQuality = (quality: string) => patch({ quality })
  const setPage = (page: number) => patch({ page })
  const setPageSize = (pageSize: number) => patch({ pageSize })
  const setSort = (next: SetStateAction<KnowledgeView["sort"]>) => patch({ sort: typeof next === "function" ? next(readKnowledgeView(window.location.search, defaults).sort) : next })
  const setPreferences = (next: SetStateAction<Preferences>) => {
    const latest = readKnowledgeView(window.location.search, defaults)
    patch(typeof next === "function" ? next({ columns: latest.columns, compact: latest.compact }) : next)
  }
  const preferenceColumns = preferences.columns.join(",")
  const compact = preferences.compact

  useEffect(() => {
    try { localStorage.setItem(preferencesKey, JSON.stringify({ columns: preferenceColumns ? preferenceColumns.split(",") : [], compact })) }
    catch { /* Display controls still work for the current visit. */ }
  }, [preferenceColumns, compact, preferencesKey])

  const filtered = documents.filter((doc) => doc.source_id.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
    && (!status || doc.status === status) && (!quality || qualityKey(doc) === quality))
    .sort((a, b) => {
      const value = (doc: DocumentRecord): string | number | null => sort.key === "quality" ? qualitySummary(doc.ingestion_quality).label
        : sort.key === "last_synced_at" ? (Number.isFinite(Date.parse(doc.last_synced_at)) ? Date.parse(doc.last_synced_at) : null) : doc[sort.key]
      const left = value(a), right = value(b)
      if (left == null && right == null) return a.source_id.localeCompare(b.source_id)
      if (left == null) return 1
      if (right == null) return -1
      const comparison = typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right), undefined, { numeric: true })
      return (sort.descending ? -comparison : comparison) || a.source_id.localeCompare(b.source_id)
    })
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pageCount - 1)
  const visible = filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
  const headers: { key: SortKey; label: string }[] = [{ key: "source_id", label: "Name" }, ...columns.filter((column) => preferences.columns.includes(column.key))]
  const filteredActive = Boolean(search || status || quality)

  function sortBy(key: SortKey) {
    setSort((value) => ({ key, descending: value.key === key ? !value.descending : false }))
    setPage(0)
  }

  function cell(doc: DocumentRecord, key: SortKey) {
    switch (key) {
      case "source_id": return <button type="button" onClick={() => onOpen(doc)} className="max-w-80 truncate rounded text-left font-medium hover:text-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" title={doc.source_id}>{doc.source_id}</button>
      case "version": return <span className="font-technical">v{doc.version}</span>
      case "chunk_count": return <span className="font-technical">{doc.chunk_count ?? "—"}</span>
      case "quality": { const summary = qualitySummary(doc.ingestion_quality); return <Badge variant={summary.status}>{summary.label}</Badge> }
      case "status": return <StatusBadge status={doc.status} />
      case "last_synced_at": return <span title={doc.last_synced_at}>{formatRelativeTime(doc.last_synced_at)}</span>
    }
  }

  return <div>
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] pb-4">
      <div className="flex min-w-40 flex-1 items-center gap-2 rounded-md border border-[var(--color-border)] px-2.5 focus-within:ring-2 focus-within:ring-[var(--color-accent)]">
        <Search className="h-3.5 w-3.5 text-[var(--color-subtle-foreground)]" />
        <input aria-label="Filter documents by name" placeholder="Filter by name…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }} className="h-8 min-w-0 flex-1 bg-transparent text-xs outline-none" />
      </div>
      <select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0) }} className={controlClass}>
        <option value="">All statuses</option>
        {[...new Set(documents.map((doc) => doc.status))].sort().map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
      <select aria-label="Filter by parse quality" value={quality} onChange={(event) => { setQuality(event.target.value); setPage(0) }} className={controlClass}>
        <option value="">All quality</option><option value="review">Needs review only</option><option value="ok">OK</option><option value="missing">Quality not reported</option>
      </select>
      <select aria-label="Table density" value={preferences.compact ? "compact" : "comfortable"} onChange={(event) => setPreferences((value) => ({ ...value, compact: event.target.value === "compact" }))} className={controlClass}>
        <option value="comfortable">Comfortable</option><option value="compact">Compact</option>
      </select>
      <Popover.Root>
        <Popover.Trigger className={cn(controlClass, "flex items-center gap-1.5")}><Columns3 className="h-3.5 w-3.5" /> Columns</Popover.Trigger>
        <Popover.Portal><Popover.Content aria-label="Visible document columns" align="end" sideOffset={6} className="z-40 w-48 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-pop">
          <p className="mb-2 text-xs font-medium">Visible columns</p>
          {columns.map((column) => <label key={column.key} className="flex min-h-8 items-center gap-2 text-xs">
            <input type="checkbox" checked={preferences.columns.includes(column.key)} onChange={() => setPreferences((value) => ({ ...value, columns: value.columns.includes(column.key) ? value.columns.filter((key) => key !== column.key) : [...value.columns, column.key] }))} />{column.label}
          </label>)}
        </Popover.Content></Popover.Portal>
      </Popover.Root>
      <KnowledgeSavedViews view={view} storageKey={`${preferencesKey}:views`} />
      <ShareViewButton values={knowledgeViewQuery({ ...view, page: currentPage })} />
      {filteredActive && <button type="button" onClick={() => { setSearch(""); setStatus(""); setQuality(""); setPage(0) }} className="h-8 rounded-md px-2 text-xs text-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">Clear filters</button>}
    </div>
    {organizationScope && selectedDocuments.length > 0 && <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md bg-[var(--color-accent-muted)] p-2 text-xs"><span>{selectedDocuments.length} selected</span><CollectionPicker scope={organizationScope} documents={selectedDocuments.map(documentReference)} onAdded={() => setSelected(new Set())} /><button type="button" onClick={() => setSelected(new Set())} className="ml-auto px-2 text-[var(--color-accent)]">Clear selection</button></div>}
    <div aria-live="polite" className="py-3 text-xs text-[var(--color-subtle-foreground)]">{filtered.length} of {documents.length} loaded documents</div>
    {filtered.length === 0 ? <EmptyState title={filteredActive ? "No documents match" : "No documents yet"} description={filteredActive ? "Adjust or clear your filters to see more documents." : "This source has no indexed documents."} /> : <>
      <div className="overflow-x-auto">
        <table aria-label="Knowledge documents" className="w-full text-left text-xs">
          <thead><tr className="border-b border-[var(--color-border)] text-[var(--color-muted-foreground)]">
            {organizationScope && <th className="w-8 py-2 pr-3"><input type="checkbox" aria-label="Select documents on this page" checked={visible.length > 0 && visible.every((document) => selected.has(documentKey(documentReference(document))))} onChange={(event) => setSelected((value) => { const next = new Set(value); for (const document of visible) { const key = documentKey(documentReference(document)); if (event.target.checked) next.add(key); else next.delete(key) } return next })} /></th>}
            {headers.map((column) => <th key={column.key} aria-sort={sort.key === column.key ? sort.descending ? "descending" : "ascending" : "none"} className="whitespace-nowrap px-3 py-2 font-medium first:pl-0">
              <button type="button" onClick={() => sortBy(column.key)} aria-label={`Sort by ${column.label}`} className="flex min-h-7 items-center gap-1.5 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
                {column.label}{sort.key === column.key ? sort.descending ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" /> : <ArrowUpDown className="h-3 w-3 opacity-40" />}
              </button>
            </th>)}
          </tr></thead>
          <tbody>{visible.map((doc) => <tr key={`${doc.source_type}:${doc.source_id}`} onClick={() => onOpen(doc)} className="cursor-pointer border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-hover)]">
            {organizationScope && <td className="py-2 pr-3" onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={`Select ${doc.source_id}`} checked={selected.has(documentKey(documentReference(doc)))} onChange={() => setSelected((value) => { const next = new Set(value), key = documentKey(documentReference(doc)); if (next.has(key)) next.delete(key); else next.add(key); return next })} /></td>}
            {headers.map((column) => <td key={column.key} className={cn("whitespace-nowrap px-3 text-[var(--color-muted-foreground)] first:pl-0 first:text-[var(--color-foreground)]", preferences.compact ? "py-1.5" : "py-3")}>{cell(doc, column.key)}</td>)}
          </tr>)}</tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] pt-3 text-xs text-[var(--color-muted-foreground)]">
        <label className="flex items-center gap-2">Rows per page<select aria-label="Rows per page" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(0) }} className={controlClass}>{[10, 25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
        <div className="flex items-center gap-3"><span>Page {currentPage + 1} of {pageCount}</span>
          <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} className="min-h-8 rounded px-2 hover:bg-[var(--color-surface-hover)] disabled:opacity-40">Previous</button>
          <button type="button" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)} className="min-h-8 rounded px-2 hover:bg-[var(--color-surface-hover)] disabled:opacity-40">Next</button>
        </div>
      </div>
    </>}
  </div>
}
