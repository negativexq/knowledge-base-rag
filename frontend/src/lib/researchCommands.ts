import { History } from "lucide-react"
import type { ResearchSession } from "@/lib/research"
import type { WorkspaceCommand } from "@/lib/workspaceCommands"

interface Actions {
  sessions: ResearchSession[]
  active: { id: string }
  rename: (id: string, title: string) => void
  star: (id: string) => void
  pinSession: (id: string) => void
  remove: (id: string) => void
  restoreSession: (session: ResearchSession) => void
}
export function researchSessionCommands(library: Actions, onOpen: (id: string) => void, disabled: boolean, onRemove = library.remove): WorkspaceCommand[] {
  return library.sessions.slice().sort((a, b) => Number(b.pinned) - Number(a.pinned) || Number(b.starred) - Number(a.starred) || b.updatedAt.localeCompare(a.updatedAt)).map((session) => ({
    id: `research-open-${session.id}`, label: `Open research: ${session.title}`, icon: History, disabled, run: () => onOpen(session.id),
    conversation: { session, active: session.id === library.active.id, rename: (title) => library.rename(session.id, title), star: () => library.star(session.id), pin: () => library.pinSession(session.id), remove: () => onRemove(session.id), restore: () => library.restoreSession(session) },
  }))
}
