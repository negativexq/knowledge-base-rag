import { CheckCircle2, CircleAlert, X } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"

import { queueResearch } from "@/lib/organization"
import { dismissFinished, OPEN_RESEARCH_EVENT, useResearchRuns, type FinishedRun } from "@/lib/researchRuns"

const OUTCOME: Record<FinishedRun["outcome"], string> = {
  answered: "Research finished",
  unverified: "Research finished without a verified answer",
  stopped: "Research stopped",
}

// Reports research that finished while the person was elsewhere, with a
// way back to it.
export function ResearchRunNotices() {
  const { finished } = useResearchRuns()
  const navigate = useNavigate()
  const location = useLocation()
  if (finished.length === 0) return null

  function open(run: FinishedRun) {
    dismissFinished(run.sessionId)
    if (location.pathname === "/playground") window.dispatchEvent(new CustomEvent(OPEN_RESEARCH_EVENT, { detail: run.sessionId }))
    else if (queueResearch(run.scope, run.sessionId, null)) navigate("/playground")
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(360px,calc(100vw-32px))] flex-col gap-2" aria-live="polite">
      {finished.slice(-3).map((run) => {
        const Icon = run.outcome === "answered" ? CheckCircle2 : CircleAlert
        return (
          <div key={run.sessionId} role="status" className="pointer-events-auto flex items-start gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm shadow-card">
            <Icon className={run.outcome === "answered" ? "mt-0.5 h-4 w-4 shrink-0 text-[var(--color-success)]" : "mt-0.5 h-4 w-4 shrink-0 text-[var(--color-warning)]"} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{OUTCOME[run.outcome]}</p>
              <p className="truncate text-xs text-[var(--color-muted-foreground)]" title={run.question}>{run.question}</p>
              <button type="button" onClick={() => open(run)} className="mt-1.5 text-xs font-medium text-[var(--color-accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">Open answer</button>
            </div>
            <button type="button" aria-label="Dismiss" onClick={() => dismissFinished(run.sessionId)} className="rounded p-0.5 text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)]"><X className="h-3.5 w-3.5" /></button>
          </div>
        )
      })}
    </div>
  )
}
