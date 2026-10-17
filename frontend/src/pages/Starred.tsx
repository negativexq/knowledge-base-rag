import { useState } from "react"
import { ArrowUpRight, MessageSquare, Search, Star } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { EmptyState } from "@/components/EmptyState"
import { IdentityScope } from "@/components/IdentityScope"
import { useResearchLibrary } from "@/hooks/useResearchLibrary"
import { queueResearch } from "@/lib/organization"
import { researchSessionCommands } from "@/lib/researchCommands"
import { useRegisterWorkspaceCommands } from "@/lib/workspaceCommands"
import { formatRelativeTime } from "@/lib/utils"

export default function Starred() {
  return <IdentityScope>{(scope) => <StarredWorkspace key={scope} scope={scope} />}</IdentityScope>
}

function StarredWorkspace({ scope }: { scope: string }) {
  const library = useResearchLibrary(scope)
  const navigate = useNavigate()
  const [search, setSearch] = useState("")
  const [error, setError] = useState("")
  const [removed, setRemoved] = useState<{ id: string; title: string } | null>(null)
  const starred = library.sessions.filter((session) => session.starred).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  const matches = starred.filter((session) => session.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  function open(id: string) {
    if (queueResearch(scope, id, null)) navigate("/playground")
    else setError("This browser could not open the conversation. Session storage is unavailable.")
  }
  useRegisterWorkspaceCommands(researchSessionCommands(library, open, false))

  return <div className="mx-auto flex max-w-5xl flex-col gap-5 px-5 py-7 sm:px-8">
    <p className="text-sm leading-6 text-[var(--color-muted-foreground)]">Quick access to your starred conversations. Star a conversation from its three-dot menu in Research.</p>
    {(error || library.storageError) && <p role="status" className="text-xs text-[var(--color-warning)]">{error || "Browser storage is unavailable or full. Changes may not be retained."}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex w-full max-w-sm items-center gap-2 rounded-md border border-[var(--color-border)] px-3"><Search className="h-4 w-4 text-[var(--color-subtle-foreground)]" /><input aria-label="Search starred conversations" placeholder="Search starred conversations…" value={search} onChange={(event) => setSearch(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" /></div>
      <span className="text-xs text-[var(--color-subtle-foreground)]">{starred.length} starred</span>
    </div>
    {removed && <div role="status" className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] p-3 text-xs"><span>Removed {removed.title} from Starred.</span><button type="button" onClick={() => { if (library.sessions.some((session) => session.id === removed.id && !session.starred)) library.star(removed.id); setRemoved(null) }} className="shrink-0 font-medium text-[var(--color-accent)]">Undo unstar</button></div>}
    {starred.length === 0 ? <EmptyState icon={Star} title="No starred conversations yet" description="Use Star in a conversation's menu to keep it close at hand. Your conversations remain in Research." /> : matches.length === 0 ? <EmptyState icon={Search} title="No matching conversations" description="Try a different conversation title." /> : <ul aria-label="Starred conversations" className="divide-y divide-[var(--color-border)]">{matches.map((session) => <li key={session.id} className="flex items-center gap-3 py-4">
      <MessageSquare className="h-4 w-4 shrink-0 text-[var(--color-subtle-foreground)]" />
      <button type="button" onClick={() => open(session.id)} aria-label={`Open conversation: ${session.title}`} className="group min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><span className="flex items-center gap-2 text-sm font-medium"><span className="truncate">{session.title}</span><ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-[var(--color-subtle-foreground)] group-hover:text-[var(--color-accent)]" /></span><span className="mt-1 block text-xs text-[var(--color-subtle-foreground)]">{session.turns.length} questions · {formatRelativeTime(session.updatedAt)}</span></button>
      <button type="button" aria-label={`Unstar ${session.title}`} title="Remove from Starred" onClick={() => { library.star(session.id); setRemoved({ id: session.id, title: session.title }) }} className="rounded-md p-2 text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><Star className="h-4 w-4 fill-current" /></button>
    </li>)}</ul>}
  </div>
}
