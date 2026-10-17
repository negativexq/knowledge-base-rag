import { useState } from "react"
import { Dialog } from "radix-ui"
import { Columns2, NotebookPen, Pin, X } from "lucide-react"

import { EmptyState } from "@/components/EmptyState"
import { resolvePin, type EvidencePin, type ResearchSession } from "@/lib/research"

const pinKey = (pin: EvidencePin) => `${pin.turnIndex}:${pin.sourceRank}:${pin.supportId}`

export function PinnedEvidence({ session, onOpen, onRemove, onAddNote }: {
  session: ResearchSession
  onOpen: (pin: EvidencePin) => void
  onRemove: (pin: EvidencePin) => void
  onAddNote?: (pin: EvidencePin) => void
}) {
  const [selected, setSelected] = useState<string[]>([])
  const [comparing, setComparing] = useState(false)
  const entries = session.pins.map((pin) => ({ pin, evidence: resolvePin(session, pin) })).filter((entry) => entry.evidence)
  const pair = entries.filter((entry) => selected.includes(pinKey(entry.pin)))
  if (!entries.length) return <EmptyState icon={Pin} title="No pinned evidence" description="Pin a source or a cited passage to keep it with this research." />
  return <div className="space-y-3">
    <p className="text-xs text-[var(--color-muted-foreground)]">Select two passages to compare their source text and context.</p>
    <button type="button" disabled={pair.length !== 2} onClick={() => setComparing(true)} className="flex min-h-8 items-center gap-2 rounded-md border border-[var(--color-border)] px-3 text-xs font-medium hover:bg-[var(--color-surface-hover)] disabled:opacity-40"><Columns2 className="h-3.5 w-3.5" />Compare selected ({pair.length}/2)</button>
    {entries.map(({ pin, evidence }, index) => <article key={pinKey(pin)} className="rounded-lg border border-[var(--color-border)] p-3">
      <div className="flex items-start gap-2">
        <input type="checkbox" aria-label={`Compare evidence ${index + 1}`} checked={selected.includes(pinKey(pin))} disabled={pair.length >= 2 && !selected.includes(pinKey(pin))} onChange={() => setSelected((value) => value.includes(pinKey(pin)) ? value.filter((key) => key !== pinKey(pin)) : [...value.filter((key) => entries.some((entry) => pinKey(entry.pin) === key)), pinKey(pin)])} className="mt-1" />
        <button type="button" onClick={() => onOpen(pin)} className="min-w-0 flex-1 text-left text-[13px] font-medium text-[var(--color-accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">{evidence!.source.source_id ?? "Unknown source"}</button>
        <button type="button" aria-label={`Unpin evidence from ${evidence!.source.source_id ?? "unknown"}`} onClick={() => { setSelected((value) => value.filter((key) => key !== pinKey(pin))); onRemove(pin) }} className="rounded p-1 text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]"><X className="h-3.5 w-3.5" /></button>
      </div>
      <p className="mt-1 text-[11px] text-[var(--color-subtle-foreground)]">Question {pin.turnIndex + 1}{evidence!.source.page_number != null ? ` · Page ${evidence!.source.page_number}` : ""}{evidence!.unit?.section_label ? ` · ${evidence!.unit.section_label}` : ""}</p>
      <p className="mt-2 line-clamp-6 whitespace-pre-wrap border-l-2 border-[var(--color-border-strong)] pl-3 text-[13px] leading-6">{evidence!.text || "No preview available."}</p>
      {onAddNote && <button type="button" onClick={() => onAddNote(pin)} className="mt-2 flex min-h-7 items-center gap-1.5 rounded px-1 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]"><NotebookPen className="h-3.5 w-3.5" />Add linked note</button>}
    </article>)}
    <Dialog.Root open={comparing && pair.length === 2} onOpenChange={setComparing}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-pop">
          <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] p-5"><div><Dialog.Title className="text-base font-semibold">Evidence comparison</Dialog.Title><Dialog.Description className="mt-1 text-xs text-[var(--color-muted-foreground)]">Compare the captured passages, document versions and locations.</Dialog.Description></div><Dialog.Close aria-label="Close evidence comparison" className="rounded p-1.5 hover:bg-[var(--color-surface-hover)]"><X className="h-4 w-4" /></Dialog.Close></div>
          <div className="grid min-h-0 overflow-y-auto md:grid-cols-2">{pair.map(({ pin, evidence }, index) => <section key={pinKey(pin)} aria-label={`Comparison passage ${index + 1}`} className="min-w-0 border-b border-[var(--color-border)] p-5 md:border-b-0 md:first:border-r">
            <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-subtle-foreground)]">Passage {index + 1} · Question {pin.turnIndex + 1}</p>
            <h3 className="mt-2 break-words text-sm font-semibold">{evidence!.source.source_id ?? "Unknown source"}</h3>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-[var(--color-muted-foreground)]">
              <dt>Page</dt><dd>{evidence!.source.page_number ?? "Not reported"}</dd><dt>Section</dt><dd>{evidence!.unit?.section_label ?? (evidence!.source.heading_path?.join(" / ") || "Not reported")}</dd><dt>Version</dt><dd>{evidence!.source.document_version ?? "Not reported"}</dd>
            </dl>
            <p className="mt-5 whitespace-pre-wrap border-l-2 border-[var(--color-border-strong)] pl-4 text-[14px] leading-7">{evidence!.text || "No preview available."}</p>
          </section>)}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </div>
}
