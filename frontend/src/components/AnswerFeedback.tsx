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
  const [expectedAnswer, setExpectedAnswer] = useState("")
  const [expectedSource, setExpectedSource] = useState("")
  const [expectedPage, setExpectedPage] = useState("")
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle")
  async function submit() {
    setState("saving")
    try {
      await researchApi.feedback({ question: turn.question, answer: turn.answer, claim,
        reason, note, support_ids: [...new Set(turn.answer.match(/E\d+\.S\d+/g) ?? [])],
        trace_id: turn.metadata?.trace_id ?? null, expected_answer: expectedAnswer.trim(),
        expected_source: expectedSource.trim(), expected_page: Number.parseInt(expectedPage, 10) || null })
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
        <fieldset className="space-y-2">
          <legend className="text-[var(--color-muted-foreground)]">If you know the right answer (optional)</legend>
          <label className="block">Correct answer<input value={expectedAnswer} maxLength={2000} onChange={(event) => setExpectedAnswer(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
          <div className="flex gap-2">
            <label className="block flex-1">Document<input value={expectedSource} maxLength={500} list="feedback-sources" onChange={(event) => setExpectedSource(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
            <label className="block w-24">Page<input value={expectedPage} inputMode="numeric" pattern="[0-9]*" maxLength={4} onChange={(event) => setExpectedPage(event.target.value.replace(/\D/g, ""))} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
          </div>
          <datalist id="feedback-sources">{[...new Set(turn.sources?.map((source) => source.source_id).filter(Boolean))].map((id) => <option key={id!} value={id!} />)}</datalist>
        </fieldset>
        <p className="text-[var(--color-muted-foreground)]">The question, answer and citation IDs will be saved for your organization’s reviewers. A reviewer can add a confirmed correct answer to the evaluation set.</p>
        {state === "failed" && <p role="alert">Feedback could not be saved. Please retry.</p>}
        <Button size="sm" disabled={state === "saving"}>{state === "saving" ? "Saving…" : "Submit feedback"}</Button>
      </>}
    </form>}
  </div>
}
