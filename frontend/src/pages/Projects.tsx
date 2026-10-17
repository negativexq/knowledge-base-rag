import { useState } from "react"
import { Dialog, DropdownMenu } from "radix-ui"
import { ArrowLeft, FileText, FolderOpen, MessageSquare, MoreHorizontal, NotebookPen, Plus, Search, X } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { EmptyState } from "@/components/EmptyState"
import { GroupEditor } from "@/components/GroupEditor"
import { IdentityScope } from "@/components/IdentityScope"
import { useOrganization } from "@/hooks/useOrganization"
import { useSavedResearch } from "@/hooks/useSavedResearch"
import { queueResearch, type LocalProject } from "@/lib/organization"
import { useViewSearch, updateViewQuery } from "@/lib/viewState"
import { cn, formatRelativeTime } from "@/lib/utils"

export default function Projects() { return <IdentityScope>{(scope) => <ProjectWorkspace key={scope} scope={scope} />}</IdentityScope> }
const button = "flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--color-border)] px-3 text-xs font-medium hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"

function ProjectWorkspace({ scope }: { scope: string }) {
  const organization = useOrganization(scope)
  const research = useSavedResearch(scope)
  const navigate = useNavigate()
  const selectedId = new URLSearchParams(useViewSearch()).get("project")
  const selected = organization.projects.find((project) => project.id === selectedId)
  const [search, setSearch] = useState("")
  const [editor, setEditor] = useState<{ initial: LocalProject | null } | null>(null)
  const [adding, setAdding] = useState(false)
  const [tab, setTab] = useState("research")
  const [undo, setUndo] = useState<{ name: string; restore: () => void } | null>(null)
  const [error, setError] = useState("")
  const sessions = research.filter((session) => organization.assignments[session.id] === selectedId)
  const notes = sessions.flatMap((session) => session.notes.map((note) => ({ session, note })))
  const sources = [...new Map(sessions.flatMap((session) => session.turns.flatMap((turn) => turn.sources.filter((source) => source.source_id).map((source) => [JSON.stringify([source.source_type, source.source_id, source.document_version]), { source, session }] as const)))).values()]
  function launch(sessionId: string | null, panel?: string) {
    if (!queueResearch(scope, sessionId, selected?.id ?? null)) { setError("This browser could not open the research. Session storage is unavailable."); return }
    navigate(panel ? `/playground?panel=${panel}&inspector=open` : "/playground")
  }
  function save(name: string, description: string) {
    if (editor?.initial) return organization.edit("projects", editor.initial.id, name, description)
    const created = organization.create("projects", name, description)
    if (!created) return false
    updateViewQuery({ project: created.id }); setTab("research"); return true
  }

  return <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-7 sm:px-8">
    <div className="flex flex-wrap items-center justify-between gap-3"><p className="max-w-xl text-sm leading-6 text-[var(--color-muted-foreground)]">Keep related conversations, notes and referenced sources together. Personal projects are saved in this browser.</p><button type="button" onClick={() => setEditor({ initial: null })} className={cn(button, "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent)]")}><Plus className="h-4 w-4" />New project</button></div>
    {(organization.error || error) && <p role="status" className="text-xs text-[var(--color-warning)]">{organization.error || error}</p>}
    {undo && <div role="status" className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] p-3 text-xs"><span>Removed {undo.name}. Conversations remain in Research.</span><button type="button" onClick={() => { undo.restore(); setUndo(null) }} className="font-medium text-[var(--color-accent)]">Undo project removal</button></div>}
    {!selected && <>
      {selectedId && <p role="status" className="text-xs text-[var(--color-muted-foreground)]">This project is not available for the current identity.</p>}
      <div className="flex max-w-sm items-center gap-2 rounded-lg border border-[var(--color-border)] px-3"><Search className="h-4 w-4 text-[var(--color-subtle-foreground)]" /><input aria-label="Search projects" placeholder="Find a project…" value={search} onChange={(event) => setSearch(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" /></div>
      {organization.projects.length === 0 ? <EmptyState icon={FolderOpen} title="Your first project starts here" description="Create a project, then add existing research or start a new conversation." /> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{organization.projects.filter((project) => `${project.name} ${project.description}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((project) => {
        const items = research.filter((session) => organization.assignments[session.id] === project.id)
        return <button key={project.id} type="button" onClick={() => { updateViewQuery({ project: project.id }); setTab("research") }} className="flex min-h-40 flex-col items-start rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-left hover:border-[var(--color-border-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><FolderOpen className="mb-3 h-5 w-5 text-[var(--color-accent)]" /><span className="font-medium">{project.name}</span><span className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-muted-foreground)]">{project.description || "No description"}</span><span className="mt-auto pt-4 text-[11px] text-[var(--color-subtle-foreground)]">{items.length} conversations · {items.reduce((count, session) => count + session.notes.length, 0)} notes</span></button>
      })}</div>}
    </>}
    {selected && <>
      <button type="button" onClick={() => updateViewQuery({ project: null })} className="flex w-fit items-center gap-2 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"><ArrowLeft className="h-3.5 w-3.5" />All projects</button>
      <div className="flex items-start justify-between gap-4"><div><h2 className="text-2xl font-semibold tracking-tight">{selected.name}</h2>{selected.description && <p className="mt-2 max-w-2xl whitespace-pre-wrap text-sm text-[var(--color-muted-foreground)]">{selected.description}</p>}</div><DropdownMenu.Root><DropdownMenu.Trigger aria-label="Project options" className={button}><MoreHorizontal className="h-4 w-4" /></DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content align="end" className="z-40 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-pop"><DropdownMenu.Item onSelect={() => setEditor({ initial: selected })} className="cursor-default rounded px-3 py-2 text-xs outline-none data-[highlighted]:bg-[var(--color-surface-hover)]">Edit project</DropdownMenu.Item><DropdownMenu.Item onSelect={() => { const restore = organization.remove("projects", selected.id); if (restore) { setUndo({ name: selected.name, restore }); updateViewQuery({ project: null }) } }} className="cursor-default rounded px-3 py-2 text-xs text-[var(--color-error)] outline-none data-[highlighted]:bg-[var(--color-surface-hover)]">Remove project</DropdownMenu.Item></DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root></div>
      <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => launch(null)}><Plus className="h-3.5 w-3.5" />New research in project</button><button type="button" className={button} onClick={() => setAdding(true)}><MessageSquare className="h-3.5 w-3.5" />Add existing research</button></div>
      <div role="group" aria-label="Project content" className="flex flex-wrap gap-1 border-b border-[var(--color-border)] pb-2">{[{ id: "research", label: `Research (${sessions.length})`, icon: MessageSquare }, { id: "notes", label: `Notes (${notes.length})`, icon: NotebookPen }, { id: "sources", label: `Sources (${sources.length})`, icon: FileText }].map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)} className={cn("flex items-center gap-2 rounded-md px-3 py-2 text-xs", tab === id ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)]" : "text-[var(--color-muted-foreground)]")}><Icon className="h-3.5 w-3.5" />{label}</button>)}</div>
      {tab === "research" && (sessions.length ? <div className="divide-y divide-[var(--color-border)]">{sessions.map((session) => <div key={session.id} className="flex items-center justify-between gap-3 py-4"><button type="button" onClick={() => launch(session.id)} className="min-w-0 text-left"><span className="block truncate text-sm font-medium">{session.title}</span><span className="mt-1 block text-xs text-[var(--color-subtle-foreground)]">{session.turns.length} questions · {formatRelativeTime(session.updatedAt)}</span></button><button type="button" aria-label={`Remove ${session.title} from project`} onClick={() => organization.assign(session.id, null)} className="rounded p-2 text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]"><X className="h-3.5 w-3.5" /></button></div>)}</div> : <EmptyState title="No research in this project" description="Add a conversation from your history or start a new one." />)}
      {tab === "notes" && (notes.length ? <div className="grid gap-3 md:grid-cols-2">{notes.map(({ session, note }) => <article key={`${session.id}:${note.id}`} className="rounded-lg border border-[var(--color-border)] p-4"><p className="whitespace-pre-wrap text-[13px] leading-6">{note.text}</p><button type="button" onClick={() => launch(session.id, "notes")} className="mt-3 text-xs text-[var(--color-accent)] hover:underline">{session.title}</button></article>)}</div> : <EmptyState title="No project notes yet" description="Notes from conversations in this project will appear here." />)}
      {tab === "sources" && (sources.length ? <div className="divide-y divide-[var(--color-border)]">{sources.map(({ source, session }) => <div key={JSON.stringify([source.source_type, source.source_id, source.document_version])} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-sm">{source.source_id}</p><p className="mt-1 text-xs text-[var(--color-subtle-foreground)]">{source.source_type} · {source.document_version ? `Version ${source.document_version}` : "Version not reported"}</p></div><button type="button" onClick={() => launch(session.id, "sources")} className="shrink-0 text-xs text-[var(--color-accent)]">Open research</button></div>)}</div> : <EmptyState title="No referenced sources yet" description="Sources captured in this project's research will appear here." />)}
    </>}
    {editor && <GroupEditor key={editor.initial?.id ?? "new"} kind="project" initial={editor.initial} onSave={save} onClose={() => setEditor(null)} />}
    <Dialog.Root open={adding && Boolean(selected)} onOpenChange={setAdding}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/25" /><Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 flex max-h-[80dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop"><div className="flex items-center justify-between"><Dialog.Title className="text-sm font-semibold">Add research to project</Dialog.Title><Dialog.Close aria-label="Close research picker"><X className="h-4 w-4" /></Dialog.Close></div><div className="mt-4 overflow-y-auto">{research.length ? research.map((session) => <div key={session.id} className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] py-3"><span className="min-w-0 truncate text-xs">{session.title}</span><button type="button" disabled={organization.assignments[session.id] === selectedId} onClick={() => selected && organization.assign(session.id, selected.id)} className="shrink-0 rounded-md px-2 py-1.5 text-xs text-[var(--color-accent)] disabled:text-[var(--color-subtle-foreground)]">{organization.assignments[session.id] === selectedId ? "Added" : organization.assignments[session.id] ? "Move here" : "Add"}</button></div>) : <EmptyState title="No saved research yet" description="Complete a conversation in Research to add it here." />}</div></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>
}
