import { useState } from "react"
import { researchApi } from "@/api/research"
import type { FeedbackReason } from "@/api/types"
import type { ResearchTurn } from "@/lib/research"
import { Button } from "@/components/ui/button"

export function AnswerFeedback({ turn }: { turn: ResearchTurn }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<FeedbackReason>("incorrect")
  const [claim, setClaim] = useState("")
  const [note, setNote] = useState("")
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle")
  async function submit() {
    setState("saving")
    try {
      await researchApi.feedback({ question: turn.question, answer: turn.answer, claim,
        reason, note, support_ids: [...new Set(turn.answer.match(/E\d+\.S\d+/g) ?? [])],
        trace_id: turn.metadata?.trace_id ?? null })
      setState("saved")
    } catch { setState("failed") }
  }
  return <div className="text-xs">
    <button type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open) setClaim(window.getSelection()?.toString().slice(0, 8000) ?? "") }} className="rounded px-2 py-1 text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]">Report an issue</button>
    {open && <form aria-label="Answer feedback" className="mt-2 space-y-3 rounded-lg border border-[var(--color-border)] p-3" onSubmit={(event) => { event.preventDefault(); void submit() }}>
      {state === "saved" ? <p role="status">Feedback saved for review. <a href="/feedback" className="underline">View your reports</a></p> : <>
        <label className="block">Issue type<select aria-label="Issue type" value={reason} disabled={state === "saving"} onChange={(event) => setReason(event.target.value as FeedbackReason)} className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-1">{["incorrect", "unsupported", "outdated", "incomplete", "other"].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="block">Problematic claim (optional)<textarea value={claim} maxLength={8000} onChange={(event) => setClaim(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
        <label className="block">What should be corrected?<textarea value={note} maxLength={4000} onChange={(event) => setNote(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
        <p className="text-[var(--color-muted-foreground)]">The question, answer and citation IDs will be saved for your organization’s reviewers.</p>
        {state === "failed" && <p role="alert">Feedback could not be saved. Please retry.</p>}
        <Button size="sm" disabled={state === "saving"}>{state === "saving" ? "Saving…" : "Submit feedback"}</Button>
      </>}
    </form>}
  </div>
}
