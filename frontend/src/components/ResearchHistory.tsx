import { useState } from "react"
import { Dialog } from "radix-ui"
import { History, Pencil, Pin, Plus, Search, Star, Trash2, X } from "lucide-react"

import type { ResearchSession } from "@/lib/research"
import { cn, formatRelativeTime } from "@/lib/utils"

const actionClass = "flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40"

export function ResearchHistory({ sessions, activeId, streaming, open: controlledOpen, onOpenChange, onOpen, onNew, onRename, onStar, onRemove, onUndo, removedTitle, embedded = false, onPin }: {
  embedded?: boolean
  onPin?: (id: string) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
  sessions: ResearchSession[]
  activeId: string
  streaming: boolean
  onOpen: (id: string) => void
  onNew: () => void
  onRename: (id: string, title: string) => void
  onStar: (id: string) => void
  onRemove: (id: string) => void
  onUndo: () => void
  removedTitle: string | undefined
}) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = (value: boolean) => { setInternalOpen(value); onOpenChange?.(value) }
  const [search, setSearch] = useState("")
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const query = search.toLocaleLowerCase().trim()
  const filtered = sessions.filter((session) => !query || `${session.title} ${session.notes.map((note) => note.text).join(" ")} ${session.turns.map((turn) => `${turn.question} ${turn.answer}`).join(" ")}`.toLocaleLowerCase().includes(query))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || Number(b.starred) - Number(a.starred) || b.updatedAt.localeCompare(a.updatedAt))

  const content = <>        <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] p-5">
          <div>
            {embedded ? <h2 className="text-base font-semibold tracking-tight">Research history</h2> : <Dialog.Title className="text-base font-semibold tracking-tight">Research history</Dialog.Title>}
            {embedded ? <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">Saved in this browser for your current workspace and identity.</p> : <Dialog.Description className="mt-1 text-xs text-[var(--color-muted-foreground)]">Saved in this browser for your current workspace and identity.</Dialog.Description>}
          </div>
          {!embedded && <Dialog.Close aria-label="Close research history" className={actionClass}><X className="h-4 w-4" /></Dialog.Close>}
        </div>
        <div className="flex gap-2 p-4">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 focus-within:ring-2 focus-within:ring-[var(--color-accent)]">
            <Search className="h-4 w-4 text-[var(--color-subtle-foreground)]" />
            <input aria-label="Search research history" placeholder="Search questions and answers…" value={search} onChange={(event) => setSearch(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" />
          </div>
          <button type="button" disabled={streaming} onClick={() => { onNew(); setOpen(false) }} className="flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> New</button>
        </div>
        <div className="min-h-0 overflow-y-auto px-4 pb-4">
          {filtered.length === 0 && <p className="py-10 text-center text-sm text-[var(--color-muted-foreground)]">{query ? "No research matches your search." : "Your completed research will appear here."}</p>}
          <ul className="space-y-1">
            {filtered.map((session) => <li key={session.id} className={cn("rounded-lg border p-3", session.id === activeId ? "border-[var(--color-border-strong)] bg-[var(--color-surface-raised)]" : "border-transparent hover:bg-[var(--color-surface-hover)]")}>
              {editing === session.id ? <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); onRename(session.id, title); setEditing(null) }}>
                <input autoFocus aria-label="Research title" maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} className="h-9 min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-transparent px-2 text-sm" />
                <button type="submit" disabled={!title.trim()} className="text-xs font-medium text-[var(--color-accent)] disabled:opacity-40">Save</button>
                <button type="button" onClick={() => setEditing(null)} className="text-xs text-[var(--color-muted-foreground)]">Cancel</button>
              </form> : <div className="flex items-center gap-2">
                <button type="button" disabled={streaming} aria-current={session.id === activeId ? "page" : undefined} onClick={() => { onOpen(session.id); setOpen(false) }} className="min-w-0 flex-1 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-50">
                  <span className="block truncate text-[13px] font-medium">{session.title}</span>
                  <span className="mt-1 block text-[11px] text-[var(--color-muted-foreground)]">{session.turns.filter((turn) => !turn.streaming).length} {session.turns.filter((turn) => !turn.streaming).length === 1 ? "question" : "questions"} · {formatRelativeTime(session.updatedAt)}{session.pins.length > 0 ? ` · ${session.pins.length} pinned` : ""}</span>
                </button>
                <button type="button" aria-label={`${session.starred ? "Unstar" : "Star"} ${session.title}`} aria-pressed={session.starred} onClick={() => onStar(session.id)} className={actionClass}><Star className={cn("h-3.5 w-3.5", session.starred && "fill-[var(--color-accent)] text-[var(--color-accent)]")} /></button>
                {onPin && <button type="button" aria-label={`${session.pinned ? "Unpin" : "Pin"} ${session.title}`} aria-pressed={session.pinned} onClick={() => onPin(session.id)} className={actionClass}><Pin className={cn("h-3.5 w-3.5", session.pinned && "text-[var(--color-accent)]")} /></button>}
                <button type="button" aria-label={`Rename ${session.title}`} onClick={() => { setEditing(session.id); setTitle(session.title) }} className={actionClass}><Pencil className="h-3.5 w-3.5" /></button>
                <button type="button" disabled={streaming} aria-label={`Remove ${session.title}`} onClick={() => onRemove(session.id)} className={actionClass}><Trash2 className="h-3.5 w-3.5" /></button>
              </div>}
            </li>)}
          </ul>
        </div>
        {streaming && <p className="px-5 pb-3 text-xs text-[var(--color-muted-foreground)]">Finish or stop the current answer to switch research.</p>}
        {removedTitle && <div role="status" className="flex items-center justify-between gap-3 border-t border-[var(--color-border)] p-4 text-xs"><span className="truncate">Removed {removedTitle}</span><button type="button" onClick={onUndo} className="font-medium text-[var(--color-accent)]">Undo</button></div>}</>
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    {embedded ? <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">{content}</div> : <>
      <Dialog.Trigger asChild><button type="button" className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><History className="h-3.5 w-3.5" /> History</button></Dialog.Trigger>
      <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85dvh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-pop">{content}</Dialog.Content></Dialog.Portal>
    </>}
  </Dialog.Root>
}
