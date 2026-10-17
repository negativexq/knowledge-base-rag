import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Dialog, DropdownMenu } from "radix-ui"
import { ArrowLeft, FileText, Folders, MoreHorizontal, Plus, Search, X } from "lucide-react"
import { sourcesApi } from "@/api/sources"
import { classifyError } from "@/api/client"
import { EmptyState } from "@/components/EmptyState"
import { ErrorState } from "@/components/ErrorState"
import { GroupEditor } from "@/components/GroupEditor"
import { IdentityScope } from "@/components/IdentityScope"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { useOrganization } from "@/hooks/useOrganization"
import { documentKey, documentReference, type LocalProject } from "@/lib/organization"
import { useViewSearch, updateViewQuery } from "@/lib/viewState"
import { cn } from "@/lib/utils"

export default function Collections() { return <IdentityScope>{(scope) => <CollectionWorkspace key={scope} scope={scope} />}</IdentityScope> }
const button = "flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--color-border)] px-3 text-xs font-medium hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
function CollectionWorkspace({ scope }: { scope: string }) {
  const organization = useOrganization(scope)
  const selectedId = new URLSearchParams(useViewSearch()).get("collection")
  const selected = organization.collections.find((collection) => collection.id === selectedId)
  const [search, setSearch] = useState("")
  const [editor, setEditor] = useState<{ initial: LocalProject | null } | null>(null)
  const [adding, setAdding] = useState(false)
  const [documentSearch, setDocumentSearch] = useState("")
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [undo, setUndo] = useState<{ name: string; restore: () => void } | null>(null)
  const documents = useQuery({ queryKey: ["documents", scope, "collections"], queryFn: () => sourcesApi.documents(), enabled: Boolean(selected) })
  const available = documents.data ?? []
  const indexed = new Map(available.map((document) => [documentKey(documentReference(document)), document]))
  function save(name: string, description: string) {
    if (editor?.initial) return organization.edit("collections", editor.initial.id, name, description)
    const created = organization.create("collections", name, description)
    if (!created) return false
    updateViewQuery({ collection: created.id }); return true
  }
  return <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-7 sm:px-8">
    <div className="flex flex-wrap items-center justify-between gap-3"><p className="max-w-xl text-sm leading-6 text-[var(--color-muted-foreground)]">Group document references by topic or department. Personal collections are saved in this browser.</p><button type="button" onClick={() => setEditor({ initial: null })} className={cn(button, "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent)]")}><Plus className="h-4 w-4" />New collection</button></div>
    {organization.error && <p role="status" className="text-xs text-[var(--color-warning)]">{organization.error}</p>}
    {undo && <div role="status" className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] p-3 text-xs"><span>Removed {undo.name}. Source documents are unchanged.</span><button type="button" onClick={() => { undo.restore(); setUndo(null) }} className="font-medium text-[var(--color-accent)]">Undo collection removal</button></div>}
    {!selected && <>
      {selectedId && <p role="status" className="text-xs text-[var(--color-muted-foreground)]">This collection is not available for the current identity.</p>}
      <div className="flex max-w-sm items-center gap-2 rounded-lg border border-[var(--color-border)] px-3"><Search className="h-4 w-4 text-[var(--color-subtle-foreground)]" /><input aria-label="Search collections" placeholder="Find a collection…" value={search} onChange={(event) => setSearch(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" /></div>
      {organization.collections.length === 0 ? <EmptyState icon={Folders} title="Create your first collection" description="Collect related documents here or select documents in Knowledge." /> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{organization.collections.filter((collection) => `${collection.name} ${collection.description}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((collection) => <button type="button" key={collection.id} onClick={() => updateViewQuery({ collection: collection.id })} className="flex min-h-40 flex-col items-start rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-left hover:border-[var(--color-border-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><Folders className="mb-3 h-5 w-5 text-[var(--color-accent)]" /><span className="font-medium">{collection.name}</span><span className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-muted-foreground)]">{collection.description || "No description"}</span><span className="mt-auto pt-4 text-[11px] text-[var(--color-subtle-foreground)]">{collection.documents.length} document references</span></button>)}</div>}
    </>}
    {selected && <>
      <button type="button" onClick={() => updateViewQuery({ collection: null })} className="flex w-fit items-center gap-2 text-xs text-[var(--color-muted-foreground)]"><ArrowLeft className="h-3.5 w-3.5" />All collections</button>
      <div className="flex items-start justify-between gap-4"><div><h2 className="text-2xl font-semibold tracking-tight">{selected.name}</h2>{selected.description && <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--color-muted-foreground)]">{selected.description}</p>}</div><DropdownMenu.Root><DropdownMenu.Trigger aria-label="Collection options" className={button}><MoreHorizontal className="h-4 w-4" /></DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content align="end" className="z-40 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-pop"><DropdownMenu.Item onSelect={() => setEditor({ initial: selected })} className="cursor-default rounded px-3 py-2 text-xs outline-none data-[highlighted]:bg-[var(--color-surface-hover)]">Edit collection</DropdownMenu.Item><DropdownMenu.Item onSelect={() => { const restore = organization.remove("collections", selected.id); if (restore) { setUndo({ name: selected.name, restore }); updateViewQuery({ collection: null }) } }} className="cursor-default rounded px-3 py-2 text-xs text-[var(--color-error)] outline-none data-[highlighted]:bg-[var(--color-surface-hover)]">Remove collection</DropdownMenu.Item></DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root></div>
      <button type="button" onClick={() => { setChosen(new Set()); setAdding(true) }} className={cn(button, "w-fit")}><Plus className="h-3.5 w-3.5" />Add documents</button>
      {documents.isError && <div className="space-y-2"><ErrorState kind={classifyError(documents.error)} detail={(documents.error as Error).message} /><button type="button" className={button} onClick={() => void documents.refetch()}>Retry document metadata</button></div>}
      {selected.documents.length === 0 ? <EmptyState icon={FileText} title="No documents in this collection" description="Add documents from the current Knowledge index." /> : <div className="divide-y divide-[var(--color-border)]">{selected.documents.map((reference) => {
        const document = indexed.get(documentKey(reference))
        return <div key={documentKey(reference)} className="flex items-center justify-between gap-3 py-4"><div className="min-w-0"><p className="break-words text-sm font-medium">{reference.sourceId}</p><p className="mt-1 text-xs text-[var(--color-subtle-foreground)]">{reference.sourceType} · {document ? `v${document.version} · ${document.chunk_count ?? "untracked"} chunks · ${document.status}` : documents.isLoading ? "Loading current metadata…" : documents.isError ? "Current metadata unavailable" : "Not returned by the current index"}</p></div><button type="button" aria-label={`Remove ${reference.sourceId} from collection`} onClick={() => organization.removeDocument(selected.id, reference)} className="shrink-0 rounded p-2 text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]"><X className="h-4 w-4" /></button></div>
      })}</div>}
    </>}
    {editor && <GroupEditor key={editor.initial?.id ?? "new"} kind="collection" initial={editor.initial} onSave={save} onClose={() => setEditor(null)} />}
    <Dialog.Root open={adding && Boolean(selected)} onOpenChange={setAdding}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/25" /><Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 flex max-h-[80dvh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop"><div className="flex items-center justify-between"><Dialog.Title className="text-sm font-semibold">Choose collection documents</Dialog.Title><Dialog.Close aria-label="Close document picker"><X className="h-4 w-4" /></Dialog.Close></div><input aria-label="Search available documents" placeholder="Filter documents…" value={documentSearch} onChange={(event) => setDocumentSearch(event.target.value)} className="my-4 h-9 rounded-md border border-[var(--color-border)] bg-transparent px-3 text-xs" /><div className="min-h-0 overflow-y-auto">{documents.isLoading ? <LoadingRows rows={4} /> : documents.isError ? <ErrorState kind={classifyError(documents.error)} /> : available.filter((document) => document.source_id.toLocaleLowerCase().includes(documentSearch.toLocaleLowerCase())).map((document) => {
      const key = documentKey(documentReference(document)), included = selected?.documents.some((item) => documentKey(item) === key)
      return <label key={key} className="flex items-center gap-3 border-b border-[var(--color-border)] py-3 text-xs"><input type="checkbox" aria-label={`Collect ${document.source_id}`} checked={Boolean(included) || chosen.has(key)} disabled={included} onChange={() => setChosen((value) => { const next = new Set(value); if (next.has(key)) next.delete(key); else next.add(key); return next })} /><span className="min-w-0 flex-1 truncate">{document.source_id}</span><span className="text-[var(--color-subtle-foreground)]">{included ? "Added" : document.source_type}</span></label>
    })}</div><button type="button" disabled={!chosen.size} onClick={() => { if (selected && organization.addDocuments(selected.id, available.filter((document) => chosen.has(documentKey(documentReference(document)))).map(documentReference))) setAdding(false) }} className="mt-4 min-h-9 rounded-md bg-[var(--color-accent)] px-3 text-xs text-[var(--color-accent-foreground)] disabled:opacity-40">Add {chosen.size} selected documents</button></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>
}
