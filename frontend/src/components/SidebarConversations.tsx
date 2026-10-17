import { useState, useSyncExternalStore } from "react"
import { Dialog, DropdownMenu } from "radix-ui"
import { History, MessageSquare, MoreHorizontal, Pencil, Pin, Plus, Search, Star, Trash2, X } from "lucide-react"
import type { ResearchSession } from "@/lib/research"
import { cn } from "@/lib/utils"

const menuItem = "flex cursor-default items-center gap-2 rounded px-2 py-2 text-xs outline-none data-[highlighted]:bg-[var(--color-surface-hover)] data-[disabled]:opacity-40"

const mobileQuery = "(max-width: 1023px)"
const subscribe = (listener: () => void) => {
  const media = window.matchMedia?.(mobileQuery)
  media?.addEventListener("change", listener)
  return () => media?.removeEventListener("change", listener)
}

export function SidebarConversations({ sessions, activeId, streaming, open: panelOpen, onOpenChange, onOpen, onNew, onHistory, onRename, onStar, onPin, onRemove, onRestore }: {
  sessions: ResearchSession[]
  activeId: string
  streaming: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onOpen: (id: string) => void
  onNew: () => void
  onHistory: () => void
  onRename: (id: string, title: string) => void
  onStar: (id: string) => void
  onPin: (id: string) => void
  onRemove: (id: string) => void
  onRestore: (session: ResearchSession) => void
}) {
  const mobile = useSyncExternalStore(subscribe, () => window.matchMedia?.(mobileQuery).matches ?? false, () => false)
  const [search, setSearch] = useState("")
  const [editing, setEditing] = useState<ResearchSession | null>(null)
  const [title, setTitle] = useState("")
  const [undo, setUndo] = useState<{ title: string; restore: () => void } | null>(null)
  const rows = sessions.filter((session) => session.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || Number(b.starred) - Number(a.starred) || b.updatedAt.localeCompare(a.updatedAt))
  function open(session: ResearchSession) { if (!streaming) { onOpen(session.id); if (mobile) onOpenChange(false) } }
  function create() { if (!streaming) { onNew(); if (mobile) onOpenChange(false) } }
  function rename() { if (editing && title.trim()) { onRename(editing.id, title.trim()); setEditing(null) } }
  function toggle(session: ResearchSession, key: "starred" | "pinned") { if (key === "starred") onStar(session.id); else onPin(session.id) }
  function remove(session: ResearchSession) { if (!streaming) { onRemove(session.id); setUndo({ title: session.title, restore: () => onRestore(session) }) } }

  const content = <section aria-label="Conversation history" className="flex h-full min-h-0 flex-col">
    <div className="flex h-12 shrink-0 items-center gap-1 border-b border-[var(--color-border)] px-3">
      <h2 className="mr-auto text-xs font-semibold">Conversations</h2>
      <button type="button" aria-label="New conversation" title="New conversation" disabled={streaming} onClick={create} className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40"><Plus className="h-3.5 w-3.5" /></button>
      <button type="button" aria-label="Close conversations" title="Close conversations" onClick={() => onOpenChange(false)} className="flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-accent)]/30 bg-[var(--color-accent-muted)] text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-[var(--color-accent-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><X className="h-3.5 w-3.5" /></button>
    </div>
    <button type="button" disabled={streaming} onClick={create} className="mx-3 mt-3 flex min-h-9 items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 text-xs font-medium hover:bg-[var(--color-surface-hover)] disabled:opacity-40"><Plus className="h-3.5 w-3.5" />New research</button>
    <div className="flex min-h-0 flex-1 flex-col px-2 pb-3">
      {sessions.length > 0 && <div className="mx-1 my-2 flex items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2"><Search className="h-3 w-3 text-[var(--color-subtle-foreground)]" /><input aria-label="Search conversations" maxLength={200} placeholder="Find a conversation…" value={search} onChange={(event) => setSearch(event.target.value)} className="h-7 min-w-0 flex-1 bg-transparent text-[11px] outline-none" /></div>}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.map((session, index) => {
          const selected = session.id === activeId
          const group = session.pinned ? "Pinned" : session.starred ? "Starred" : "Recent"
          const previous = rows[index - 1]
          const previousGroup = previous ? previous.pinned ? "Pinned" : previous.starred ? "Starred" : "Recent" : null
          return <div key={session.id}>
            {group !== previousGroup && <p className="px-2.5 pb-1 pt-2 text-[10px] text-[var(--color-subtle-foreground)]">{group}</p>}
            <div className={cn("group flex min-w-0 items-center rounded-md", selected && "bg-[var(--color-surface-hover)]")}>
              <button type="button" aria-label={`Open conversation: ${session.title}`} aria-current={selected ? "page" : undefined} disabled={streaming} onClick={() => open(session)} title={session.title} className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-md px-2.5 text-left text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40">
                {session.pinned ? <Pin className="h-3 w-3 shrink-0 text-[var(--color-accent)]" /> : session.starred ? <Star className="h-3 w-3 shrink-0 fill-[var(--color-accent)] text-[var(--color-accent)]" /> : <MessageSquare className="h-3 w-3 shrink-0" />}<span className="truncate">{session.title}</span>
              </button>
              <DropdownMenu.Root><DropdownMenu.Trigger aria-label={`Conversation options: ${session.title}`} className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded text-[var(--color-subtle-foreground)] hover:bg-[var(--color-surface-raised)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><MoreHorizontal className="h-3.5 w-3.5" /></DropdownMenu.Trigger>
                <DropdownMenu.Portal><DropdownMenu.Content align="start" side="right" sideOffset={6} className="z-50 min-w-44 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-pop">
                  <DropdownMenu.Item className={menuItem} onSelect={() => { setEditing(session); setTitle(session.title) }}><Pencil className="h-3.5 w-3.5" />Rename</DropdownMenu.Item>
                  <DropdownMenu.Item className={menuItem} onSelect={() => toggle(session, "starred")}><Star className="h-3.5 w-3.5" />{session.starred ? "Unstar" : "Star"}</DropdownMenu.Item>
                  <DropdownMenu.Item className={menuItem} onSelect={() => toggle(session, "pinned")}><Pin className="h-3.5 w-3.5" />{session.pinned ? "Unpin conversation" : "Pin to top"}</DropdownMenu.Item>
                  <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border)]" />
                  <DropdownMenu.Item disabled={streaming} className={cn(menuItem, "text-[var(--color-error)]")} onSelect={() => remove(session)}><Trash2 className="h-3.5 w-3.5" />Delete conversation</DropdownMenu.Item>
                </DropdownMenu.Content></DropdownMenu.Portal>
              </DropdownMenu.Root>
            </div>
          </div>
        })}
        {!rows.length && <p className="px-2.5 py-3 text-[11px] text-[var(--color-subtle-foreground)]">{search ? "No conversations match." : "Your saved conversations appear here."}</p>}
      </div>
      {undo && <div role="status" className="mx-1 mt-2 rounded-md border border-[var(--color-border)] p-2 text-[11px]"><span className="block truncate">Deleted {undo.title}</span><button type="button" onClick={() => { undo.restore(); setUndo(null) }} className="mt-1 font-medium text-[var(--color-accent)]">Undo delete</button></div>}
      <button type="button" onClick={() => { if (mobile) onOpenChange(false); onHistory() }} className="mt-3 flex min-h-8 shrink-0 items-center gap-2 rounded-md border-t border-[var(--color-border)] px-2.5 pt-2 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"><History className="h-3.5 w-3.5" />Search all conversations</button>
    </div>
    <Dialog.Root open={Boolean(editing)} onOpenChange={(open) => { if (!open) setEditing(null) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/25 backdrop-blur-sm" /><Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop">
      <div className="mb-4 flex items-center justify-between"><Dialog.Title className="text-sm font-semibold">Rename conversation</Dialog.Title><Dialog.Close aria-label="Cancel rename" className="rounded p-1"><X className="h-4 w-4" /></Dialog.Close></div>
      <form onSubmit={(event) => { event.preventDefault(); rename() }}><input aria-label="Conversation name" maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} className="h-9 w-full rounded-md border border-[var(--color-border)] bg-transparent px-2 text-sm" /><div className="mt-4 flex justify-end gap-3"><Dialog.Close className="text-xs text-[var(--color-muted-foreground)]">Cancel</Dialog.Close><button type="submit" disabled={!title.trim()} className="rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs text-[var(--color-accent-foreground)] disabled:opacity-40">Save name</button></div></form>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
  </section>
  if (mobile) return <Dialog.Root open={panelOpen} onOpenChange={onOpenChange}><Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm" />
    <Dialog.Content id="research-conversations" aria-describedby={undefined} className="fixed inset-y-0 left-0 z-40 w-72 max-w-[90vw] bg-[var(--color-surface)] shadow-pop">
      <Dialog.Title className="sr-only">Research conversations</Dialog.Title>{content}
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>
  return panelOpen ? <aside id="research-conversations" aria-label="Research conversations" className="flex w-56 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">{content}</aside> : null
}
