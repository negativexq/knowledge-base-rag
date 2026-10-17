import { useState } from "react"
import { FileText, Pencil, Trash2 } from "lucide-react"
import { resolvePin, samePin, type EvidencePin, type ResearchNote, type ResearchSession } from "@/lib/research"

export function ResearchNotes({ session, initialEvidence, disabled, onSave, onRemove, onOpen }: {
  session: ResearchSession
  initialEvidence: EvidencePin | null
  disabled: boolean
  onSave: (note: ResearchNote) => void
  onRemove: (id: string) => void
  onOpen: (pin: EvidencePin) => void
}) {
  const [text, setText] = useState("")
  const [editing, setEditing] = useState<ResearchNote | null>(null)
  const [linked, setLinked] = useState<EvidencePin | null>(initialEvidence)
  const [removed, setRemoved] = useState<ResearchNote | null>(null)
  const available = [...session.pins]
  if (linked && !available.some((pin) => samePin(pin, linked))) available.push(linked)
  const selected = linked ? available.findIndex((pin) => samePin(pin, linked)) : -1

  function save() {
    if (!text.trim() || disabled) return
    const now = new Date().toISOString()
    onSave({ id: editing?.id ?? crypto.randomUUID(), text: text.trim(), evidence: linked, createdAt: editing?.createdAt ?? now, updatedAt: now })
    setText(""); setEditing(null); setLinked(null)
  }

  return <div className="space-y-5">
    <div><h3 className="text-sm font-medium">Research notes</h3><p className="mt-1 text-xs leading-relaxed text-[var(--color-muted-foreground)]">Your observations, kept separate from generated answers and validation.</p></div>
    <form onSubmit={(event) => { event.preventDefault(); save() }} className="space-y-3 rounded-lg border border-[var(--color-border)] p-3">
      <label className="block text-xs font-medium" htmlFor="research-note">{editing ? "Edit note" : "New note"}</label>
      <textarea id="research-note" aria-label="Research note" maxLength={20000} rows={5} placeholder="Capture an observation or a question to revisit…" value={text} onChange={(event) => setText(event.target.value)} className="w-full resize-y rounded-md border border-[var(--color-border)] bg-transparent p-2 text-[13px] leading-6 outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" />
      <label className="block text-xs text-[var(--color-muted-foreground)]">Linked evidence
        <select aria-label="Note linked evidence" value={selected} onChange={(event) => setLinked(available[Number(event.target.value)] ?? null)} className="mt-1 h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs">
          <option value={-1}>No linked evidence</option>
          {available.map((pin, index) => { const evidence = resolvePin(session, pin); return <option key={index} value={index}>Question {pin.turnIndex + 1} · {evidence?.source.source_id ?? "Unavailable source"}{evidence?.unit?.section_label ? ` · ${evidence.unit.section_label}` : ""}</option> })}
        </select>
      </label>
      <div className="flex items-center gap-3"><button type="submit" disabled={!text.trim() || disabled} className="rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs font-medium text-[var(--color-accent-foreground)] disabled:opacity-40">Save note</button>
        {editing && <button type="button" onClick={() => { setEditing(null); setText(""); setLinked(null) }} className="text-xs text-[var(--color-muted-foreground)]">Cancel edit</button>}
      </div>
      {disabled && <p className="text-[11px] text-[var(--color-subtle-foreground)]">You can save this note once the current answer finishes.</p>}
    </form>
    <div className="space-y-3">{session.notes.map((note, index) => {
      const evidence = note.evidence && resolvePin(session, note.evidence)
      return <article key={note.id} className="rounded-lg border border-[var(--color-border)] p-3">
        <div className="flex items-center justify-between gap-2"><span className="text-[11px] text-[var(--color-subtle-foreground)]">Note {index + 1} · {new Date(note.updatedAt).toLocaleDateString()}</span>
          <div className="flex gap-1"><button type="button" aria-label={`Edit note ${index + 1}`} onClick={() => { setEditing(note); setText(note.text); setLinked(note.evidence) }} className="rounded p-1.5 hover:bg-[var(--color-surface-hover)]"><Pencil className="h-3.5 w-3.5" /></button>
          <button type="button" aria-label={`Remove note ${index + 1}`} disabled={disabled} onClick={() => { setRemoved(note); onRemove(note.id); if (editing?.id === note.id) { setEditing(null); setText(""); setLinked(null) } }} className="rounded p-1.5 hover:bg-[var(--color-surface-hover)] disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" /></button></div>
        </div>
        <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6">{note.text}</p>
        {evidence && <button type="button" onClick={() => onOpen(note.evidence!)} className="mt-3 flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"><FileText className="h-3.5 w-3.5" />{evidence.source.source_id ?? "Linked evidence"}{evidence.unit?.section_label ? ` · ${evidence.unit.section_label}` : ""}</button>}
      </article>
    })}</div>
    {removed && <div role="status" className="flex items-center justify-between gap-2 text-xs text-[var(--color-muted-foreground)]"><span>Note removed</span><button type="button" disabled={disabled} onClick={() => { onSave(removed); setRemoved(null) }} className="text-[var(--color-accent)] disabled:opacity-40">Undo</button></div>}
  </div>
}
