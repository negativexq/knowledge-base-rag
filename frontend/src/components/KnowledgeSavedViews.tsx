import { useEffect, useState } from "react"
import { Popover } from "radix-ui"
import { Bookmark, Trash2 } from "lucide-react"
import { knowledgeViewQuery, readKnowledgeView, type KnowledgeView } from "@/lib/knowledgeView"
import { updateViewQuery } from "@/lib/viewState"

interface SavedView { id: string; name: string; search: string }
function readViews(key: string): SavedView[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem(key) ?? "[]")
    if (!Array.isArray(values)) return []
    return values.filter((value) => value && typeof value.id === "string" && typeof value.name === "string" && typeof value.search === "string")
  } catch { return [] }
}
export function KnowledgeSavedViews({ view, storageKey }: { view: KnowledgeView; storageKey: string }) {
  const [views, setViews] = useState(() => readViews(storageKey))
  const [name, setName] = useState("")
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    void Promise.resolve().then(() => {
      try { localStorage.setItem(storageKey, JSON.stringify(views)); return false }
      catch { return true }
    }).then((error) => { if (!cancelled) setFailed(error) })
    return () => { cancelled = true }
  }, [views, storageKey])
  return <Popover.Root open={open} onOpenChange={setOpen}>
    <Popover.Trigger className="flex h-8 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2.5 text-xs focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><Bookmark className="h-3.5 w-3.5" /> Views</Popover.Trigger>
    <Popover.Portal><Popover.Content aria-label="Saved Knowledge views" align="end" sideOffset={6} className="z-40 w-80 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-pop">
      <h3 className="text-sm font-medium">Saved views</h3><p className="mt-1 text-[11px] text-[var(--color-muted-foreground)]">Filters, sorting and columns for this identity in this browser.</p>
      <div className="my-3 max-h-56 space-y-1 overflow-y-auto">{views.length ? views.map((saved) => <div key={saved.id} className="flex items-center gap-2 rounded-md hover:bg-[var(--color-surface-hover)]">
        <button type="button" onClick={() => { updateViewQuery(knowledgeViewQuery(readKnowledgeView(saved.search))); setOpen(false) }} className="min-w-0 flex-1 truncate px-2 py-2 text-left text-xs">{saved.name}</button>
        <button type="button" aria-label={`Remove saved view ${saved.name}`} onClick={() => setViews((value) => value.filter((item) => item.id !== saved.id))} className="rounded p-2 text-[var(--color-subtle-foreground)] hover:text-[var(--color-error)]"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>) : <p className="py-2 text-xs text-[var(--color-subtle-foreground)]">No saved views yet.</p>}</div>
      <form onSubmit={(event) => {
        event.preventDefault()
        if (!name.trim()) return
        const params = new URLSearchParams()
        for (const [key, value] of Object.entries(knowledgeViewQuery({ ...view, page: 0 }))) if (value !== null) params.set(key, value)
        setViews((value) => [...value, { id: crypto.randomUUID(), name: name.trim(), search: params.toString() }]); setName("")
      }} className="flex gap-2 border-t border-[var(--color-border)] pt-3">
        <input aria-label="New saved view name" placeholder="Name this view…" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} className="h-8 min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-transparent px-2 text-xs" />
        <button type="submit" disabled={!name.trim()} className="rounded-md px-2 text-xs font-medium text-[var(--color-accent)] disabled:opacity-40">Save view</button>
      </form>
      {failed && <p role="status" className="mt-2 text-xs text-[var(--color-warning)]">Browser storage is unavailable; these views last for this visit.</p>}
    </Popover.Content></Popover.Portal>
  </Popover.Root>
}
