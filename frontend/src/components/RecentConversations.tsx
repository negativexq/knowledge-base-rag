import { useState } from "react"
import { Dialog, DropdownMenu } from "radix-ui"
import { MessageSquarePlus, MoreHorizontal, Pencil, Pin, Star, Trash2, X } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { useSavedResearch } from "@/hooks/useSavedResearch"
import { queueResearch, RESEARCH_EVENT } from "@/lib/organization"
import { readResearchSessions, type ResearchSession } from "@/lib/research"
import { useWorkspaceCommands } from "@/lib/workspaceCommands"
import { cn } from "@/lib/utils"

const itemClass = "flex cursor-default items-center gap-2 rounded px-2 py-2 text-xs outline-none data-[highlighted]:bg-[var(--color-surface-hover)] data-[disabled]:opacity-40"
export function RecentConversations({ scope }: { scope: string }) {
  const saved = useSavedResearch(scope)
  const commands = useWorkspaceCommands()
  const live = commands.filter((command) => command.conversation)
  const newResearch = commands.find((command) => command.id === "research-new")
  const navigate = useNavigate()
  const records = new Map(saved.map((session) => [session.id, session]))
  for (const command of live) records.set(command.conversation!.session.id, command.conversation!.session)
  const sessions = [...records.values()].sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt.localeCompare(a.updatedAt))
  const [editing, setEditing] = useState<ResearchSession | null>(null)
  const [title, setTitle] = useState("")
  const [undo, setUndo] = useState<{ title: string; restore: () => void } | null>(null)
  const [error, setError] = useState("")
  function mutate(fn: (sessions: ResearchSession[]) => ResearchSession[]): boolean {
    try { localStorage.setItem(scope, JSON.stringify(fn(readResearchSessions(scope)))); window.dispatchEvent(new Event(RESEARCH_EVENT)); setError(""); return true }
    catch { setError("Browser storage is unavailable."); return false }
  }
  function startConversation() {
    if (newResearch) { if (!newResearch.disabled) newResearch.run() }
    else if (queueResearch(scope, null, null)) navigate("/playground")
    else setError("This browser could not start a conversation.")
  }
  function open(session: ResearchSession) {
    const command = live.find((item) => item.conversation!.session.id === session.id)
    if (command) { if (!command.disabled) command.run() }
    else if (queueResearch(scope, session.id, null)) navigate("/playground")
    else setError("This browser could not open the conversation.")
  }
  function rename() {
    if (!editing || !title.trim()) return
    const action = live.find((item) => item.conversation!.session.id === editing.id)?.conversation
    if (action) action.rename(title.trim())
    else if (!mutate((sessions) => sessions.map((session) => session.id === editing.id ? { ...session, title: title.trim(), customTitle: true } : session))) return
    setEditing(null)
  }
  function toggle(session: ResearchSession, key: "starred" | "pinned") {
    const action = live.find((item) => item.conversation!.session.id === session.id)?.conversation
    if (action) { if (key === "starred") action.star(); else action.pin() }
    else mutate((sessions) => sessions.map((item) => item.id === session.id ? { ...item, [key]: !item[key] } : item))
  }
  function remove(session: ResearchSession) {
    const action = live.find((item) => item.conversation!.session.id === session.id)?.conversation
    if (action) { action.remove(); setUndo({ title: session.title, restore: action.restore }) }
    else if (mutate((sessions) => sessions.filter((item) => item.id !== session.id))) setUndo({ title: session.title, restore: () => { mutate((sessions) => sessions.some((item) => item.id === session.id) ? sessions : [...sessions, session]) } })
  }
  return <div className="relative ml-7 hidden min-w-0 border-l border-[var(--color-border)] pl-2 md:block">
    <button type="button" onClick={startConversation} disabled={newResearch?.disabled} className="mt-1 flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40"><MessageSquarePlus className="h-3.5 w-3.5 shrink-0" />New chat</button>
    {sessions.length > 0 && <div role="list" aria-label="Recent conversations" className="mt-1 max-h-40 overflow-y-auto overscroll-contain pr-0.5">
      {sessions.map((session) => {
        const command = live.find((item) => item.conversation!.session.id === session.id)
        return <div role="listitem" key={session.id} className="flex h-8 min-w-0 items-center rounded-md hover:bg-[var(--color-surface-hover)]">
          <button type="button" aria-label={`Open conversation: ${session.title}`} disabled={command?.disabled} title={session.title} onClick={() => open(session)} className="flex h-8 min-w-0 flex-1 items-center gap-1.5 rounded px-2 text-left text-xs text-[var(--color-muted-foreground)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40">{session.pinned ? <Pin className="h-2.5 w-2.5 shrink-0 text-[var(--color-accent)]" /> : session.starred ? <Star className="h-2.5 w-2.5 shrink-0 fill-[var(--color-accent)] text-[var(--color-accent)]" /> : null}<span className="truncate">{session.title}</span></button>
          <DropdownMenu.Root><DropdownMenu.Trigger aria-label={`Conversation options: ${session.title}`} className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--color-subtle-foreground)] hover:text-[var(--color-foreground)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><MoreHorizontal className="h-3 w-3" /></DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content side="right" align="start" sideOffset={6} className="z-50 min-w-44 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-pop">
            <DropdownMenu.Item className={itemClass} onSelect={() => { setEditing(session); setTitle(session.title) }}><Pencil className="h-3.5 w-3.5" />Rename</DropdownMenu.Item>
            <DropdownMenu.Item className={itemClass} onSelect={() => toggle(session, "starred")}><Star className="h-3.5 w-3.5" />{session.starred ? "Unstar" : "Star"}</DropdownMenu.Item>
            <DropdownMenu.Item className={itemClass} onSelect={() => toggle(session, "pinned")}><Pin className="h-3.5 w-3.5" />{session.pinned ? "Unpin conversation" : "Pin to top"}</DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border)]" />
            <DropdownMenu.Item disabled={command?.disabled} className={cn(itemClass, "text-[var(--color-error)]")} onSelect={() => remove(session)}><Trash2 className="h-3.5 w-3.5" />Delete conversation</DropdownMenu.Item>
          </DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root>
        </div>
      })}
    </div>}
    {undo && <div role="status" className="absolute bottom-0 left-0 right-0 z-30 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[10px] text-[var(--color-muted-foreground)] shadow-pop"><span className="block truncate">Deleted {undo.title}</span><button type="button" onClick={() => { undo.restore(); setUndo(null) }} className="mt-1 text-[var(--color-accent)]">Undo delete</button></div>}
    {error && <p role="status" className="p-2 text-[10px] text-[var(--color-warning)]">{error}</p>}
    <Dialog.Root open={Boolean(editing)} onOpenChange={(open) => { if (!open) setEditing(null) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/25" /><Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop"><div className="mb-4 flex items-center justify-between"><Dialog.Title className="text-sm font-semibold">Rename conversation</Dialog.Title><Dialog.Close aria-label="Cancel rename"><X className="h-4 w-4" /></Dialog.Close></div><form onSubmit={(event) => { event.preventDefault(); rename() }}><input aria-label="Conversation name" maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} className="h-9 w-full rounded-md border border-[var(--color-border)] bg-transparent px-2 text-sm" /><button type="submit" disabled={!title.trim()} className="mt-4 rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs text-[var(--color-accent-foreground)] disabled:opacity-40">Save name</button></form></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>
}
