import { AnswerFeedback } from "@/components/AnswerFeedback"
import { ResearchActivity } from "@/components/ResearchActivity"
import { CalculationCard } from "@/components/CalculationCard"
import { CoverageBadge } from "@/components/CoverageBadge"
import { followUpQuestions } from "@/lib/followUps"
import { downloadAnswerReport } from "@/lib/report"
import { ClarificationPrompt } from "@/components/ClarificationPrompt"
import { ComparisonTable } from "@/components/ComparisonTable"
import { ComparisonComposer } from "@/components/ComparisonComposer"
import type { CalculationSummary, ResearchStep, Clarification, ClarificationReply, ComparisonRow } from "@/api/types"
import { useEffect, useRef, useState } from "react"
import { ArrowUp, Bell, Check, Copy, BookOpen, FileText, MessageSquarePlus, PanelRight, Download, History, NotebookPen, Pin, Columns2, Search, Share2, Sparkles, Square } from "lucide-react"

import { chatApi } from "@/api/chat"
import type {
  AnswerValidation,
  Identity,
  ChatMetadata,
  GroundingResult,
  RetrievalReportPayload,
  RetrievedSource,
  SupportUnitRef,
} from "@/api/types"
import { EvidenceSources } from "@/components/EvidenceSources"
import { ResearchNotes } from "@/components/ResearchNotes"
import { ShareViewButton } from "@/components/ShareViewButton"
import { useOrganization } from "@/hooks/useOrganization"
import { researchSessionCommands } from "@/lib/researchCommands"
import { useResearchView } from "@/hooks/useResearchView"
import { useRegisterWorkspaceCommands } from "@/lib/workspaceCommands"
import { ResearchHistory } from "@/components/ResearchHistory"
import { PinnedEvidence } from "@/components/PinnedEvidence"
import { useResearchLibrary } from "@/hooks/useResearchLibrary"
import { cancelRun, OPEN_RESEARCH_EVENT, setViewing, startRun, useResearchRuns } from "@/lib/researchRuns"
import { downloadResearch, researchOutcome, researchScope, samePin, type EvidencePin, type ResearchTurn as Turn } from "@/lib/research"
import { classifyError } from "@/api/client"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { InspectorPanel } from "@/components/InspectorPanel"
import { RetrievalPipeline } from "@/components/RetrievalPipeline"
import { SecurityInspector } from "@/components/SecurityInspector"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TraceWaterfall } from "@/components/TraceWaterfall"
import { useIdentity } from "@/hooks/useIdentity"
import { type AnswerSegment, splitAnswerIntoSegments } from "@/lib/citations"
import { AnswerBody } from "@/components/AnswerBody"
import { AnswerStatusLine } from "@/components/AnswerStatusLine"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WhyPanel } from "@/components/WhyPanel"
import { type AnswerStatus, answerStatus } from "@/lib/answerStatus"
import { cn, formatMs } from "@/lib/utils"
import { EmptyState } from "@/components/EmptyState"
import { uiApi } from "@/api/ui"
import { useQuery } from "@tanstack/react-query"
import type { ChatHistoryTurn } from "@/lib/sse"

// Completed, successful turns only: a failed or cancelled turn has no
// answer worth resolving a follow-up against. The backend keeps only the
// most recent few anyway.
function historyFrom(turns: Turn[]): ChatHistoryTurn[] {
  return turns
    .filter((turn) => !turn.streaming && !turn.errorMessage && turn.answer)
    .flatMap((turn) => [
      { role: "user" as const, content: turn.question + (turn.clarificationReply ? `\nClarification: ${turn.clarificationReply.answer}` : "") },
      { role: "assistant" as const, content: turn.answer },
    ])
}

function searchedAs(report: RetrievalReportPayload | null): string | null {
  const stage = report?.stages.find((s) => s.name === "query_rewrite")
  const query = stage?.detail?.search_query
  return typeof query === "string" ? query : null
}

function segmentsOf(turn: Turn): AnswerSegment[] {
  return splitAnswerIntoSegments(turn.answer, turn.sources, turn.metadata?.support_units ?? [])
}

function followUpsOf(turn: Turn): string[] {
  const citedUnits = segmentsOf(turn).flatMap((segment) => segment.type === "citation" && segment.valid && segment.unit ? [segment.unit] : [])
  return followUpQuestions({ question: turn.question, outcome: researchOutcome(turn), sources: turn.sources, citedUnits, calculations: calculationsOf(turn) })
}

// Calculations behind a verified answer that the answer itself cites.
function calculationsOf(turn: Turn): CalculationSummary[] {
  if (researchOutcome(turn) !== "answered") return []
  const cited = new Set(segmentsOf(turn).flatMap((segment) => segment.type === "citation" && segment.valid && segment.unit ? [segment.unit.support_id] : []))
  return (turn.metadata?.calculations ?? []).filter((calculation) => calculation.support_ids.some((id) => cited.has(id)))
}

// Support units the answer actually cites, by source card rank.
function citedUnitsByRank(turn: Turn | undefined): Map<number, SupportUnitRef[]> {
  const byRank = new Map<number, SupportUnitRef[]>()
  if (!turn) return byRank
  for (const segment of segmentsOf(turn)) {
    const unit = segment.valid ? segment.unit : undefined
    if (!unit) continue
    const units = byRank.get(unit.source_rank) ?? []
    if (!units.some((u) => u.support_id === unit.support_id)) units.push(unit)
    byRank.set(unit.source_rank, units)
  }
  return byRank
}

function statusOf(turn: Turn): AnswerStatus | null {
  return answerStatus({
    streaming: turn.streaming,
    grounding: turn.grounding,
    validation: turn.validation,
    metadata: turn.metadata,
    citesUnits: segmentsOf(turn).some((segment) => segment.unit && segment.valid),
  })
}

function isAnswerValidation(payload: unknown): payload is AnswerValidation {
  return typeof (payload as { passed?: unknown } | null)?.passed === "boolean"
}

export default function Playground() {
  const identity = useIdentity()
  if (identity.isError) return <div className="p-6"><ErrorState kind={classifyError(identity.error)} detail={(identity.error as Error).message} /></div>
  if (!identity.data) return <div className="p-6"><LoadingRows rows={3} /></div>
  return <ResearchWorkspace key={researchScope(identity.data)} identity={identity.data} />
}

function ResearchWorkspace({ identity }: { identity: Identity }) {
  const scope = researchScope(identity)
  const library = useResearchLibrary(scope)
  const organization = useOrganization(scope)
  const runs = useResearchRuns()
  const live = runs.live.get(library.active.id)
  const turns = live ? [...library.active.turns, live] : library.active.turns
  const background = runs.running.filter((run) => run.scope === scope && run.sessionId !== library.active.id)
  const [compareOpen, setCompareOpen] = useState(false)
  const [exportError, setExportError] = useState("")
  const [copiedTurn, setCopiedTurn] = useState<number | null>(null)
  const [sharingTurn, setSharingTurn] = useState<number | null>(null)
  const [question, setQuestion] = useState("")
  const workspaceView = useResearchView(researchScope(identity))
  const { mode, setMode, tab: activeTab, setTab: setActiveTab, open: inspectorOpen, setOpen: setInspectorOpen } = workspaceView
  const [historyOpen, setHistoryOpen] = useState(false)
  const [noteLink, setNoteLink] = useState<EvidencePin | null>(null)
  const [selectionVersion, setSelectionVersion] = useState(0)
  const [inspectedTurn, setInspectedTurn] = useState<number | null>(null)
  const [highlightedRank, setHighlightedRank] = useState<number | null>(null)
  const [highlightedUnit, setHighlightedUnit] = useState<string | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const sourceRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  const current = turns[turns.length - 1]
  const evidenceTurn = turns[inspectedTurn ?? turns.length - 1]

  // Leaving the page or the session no longer cancels research: it keeps
  // running and reports back when it finishes.
  useEffect(() => {
    setViewing(library.active.id)
    return () => setViewing(null)
  }, [library.active.id])

  function exportResearch() {
    try { downloadResearch(library.active); setExportError("") }
    catch { setExportError("The Markdown file could not be downloaded. Try again.") }
  }

  async function shareReport(index: number, turn: Turn) {
    setSharingTurn(index)
    try { await downloadAnswerReport(turn) } finally { setSharingTurn(null) }
  }

  async function copyAnswer(index: number, answer: string) {
    try {
      await navigator.clipboard.writeText(answer)
      setCopiedTurn(index)
      setTimeout(() => setCopiedTurn((value) => (value === index ? null : value)), 1500)
    } catch {
      // Clipboard blocked: nothing to report beyond the unchanged button.
    }
  }

  const traceQuery = useQuery({
    queryKey: ["trace", evidenceTurn?.metadata?.trace_id],
    queryFn: () => uiApi.trace(evidenceTurn!.metadata!.trace_id),
    enabled: inspectorOpen && Boolean(evidenceTurn?.metadata?.trace_id) && activeTab === "trace",
    refetchInterval: (query) => (query.state.data?.available ? false : 2000),
  })

  async function ask(overrideQuestion?: string, clarification?: ClarificationReply, sourceIds?: string[], parentTraceId?: string) {
    const q = (overrideQuestion ?? question).trim()
    if (!q || current?.streaming) return
    const history = historyFrom(turns)
    setQuestion("")
    requestAnimationFrame(() => fitComposer(composerRef.current))
    const run = startRun(scope, library.active.id, {
        question: q,
        sourceIds,
        clarificationReply: clarification,
        steps: [],
        clarification: null,
        comparison: [],
        answer: "",
        sources: [],
        report: null,
        grounding: null,
        validation: null,
        metadata: null,
        streaming: true,
        errorMessage: null,
        firstTokenAt: null,
        lastTokenAt: null,
        groundingAt: null,
        askStartedAt: performance.now(),
        researchStartedAt: Date.now(),
    })
    setInspectedTurn(null)
    setActiveTab("sources")
    setHighlightedRank(null)
    setHighlightedUnit(null)

    const patchTurn = (patch: Partial<Turn>) => run.update((turn) => ({ ...turn, ...patch }))
    let answerBuffer = ""
    let firstTokenAt: number | null = null
    await chatApi.ask(
      q,
      history,
      {
        onProgress: (payload) => {
          const step = payload as ResearchStep
          run.update((turn) => {
            const steps = [...(turn.steps ?? [])]
            const index = steps.findIndex((item) => item.id === step.id)
            // Elapsed time per step comes from the browser clock, not the server.
            const receivedAt = index < 0 ? Date.now() : steps[index].receivedAt
            if (index < 0) steps.push({ ...step, receivedAt }); else steps[index] = { ...step, receivedAt }
            return { ...turn, steps }
          })
        },
        onClarification: (payload) => patchTurn({ clarification: payload as Clarification }),
        onComparison: (payload) => patchTurn({ comparison: (payload as { rows: ComparisonRow[] }).rows }),
        onSources: (sources) => patchTurn({ sources: sources as RetrievedSource[] }),
        onRetrieval: (report) => patchTurn({ report: report as RetrievalReportPayload }),
        onSecurity: (security) => {
          if (isAnswerValidation(security)) {
            patchTurn({ validation: security, groundingAt: performance.now() })
          }
          run.update((currentTurn) => currentTurn.report ? {
            ...currentTurn,
            report: {
              ...currentTurn.report,
              security: { ...currentTurn.report.security, ...(security as object) },
            },
          } : currentTurn)
        },
        onMetadata: (metadata) => run.update((turn) => ({ ...turn, metadata: { ...turn.metadata, ...(metadata as ChatMetadata) } })),
        onToken: (token) => {
          if (firstTokenAt === null) firstTokenAt = performance.now()
          answerBuffer += token
          patchTurn({ answer: answerBuffer, firstTokenAt, lastTokenAt: performance.now() })
        },
        onGrounding: (grounding) =>
          patchTurn({ grounding: grounding as GroundingResult, groundingAt: performance.now() }),
        onDone: () => run.finish(),
        onError: (message) => run.finish({ errorMessage: message }),
      },
      run.signal,
      { ...(sourceIds?.length ? { source_ids: sourceIds } : {}), ...(clarification ? { clarification } : {}), ...(parentTraceId && /^[a-f0-9]{32}$/.test(parentTraceId) ? { parent_trace_id: parentTraceId } : {}) },
    )
  }

  // The composer grows with its text up to its max height, then scrolls.
  function fitComposer(el: HTMLTextAreaElement | null) {
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }

  function newChat() {
    const nextSessionId = library.newSession()
    const projectId = organization.assignments[library.active.id]
    if (projectId) organization.assign(nextSessionId, projectId)
    setNoteLink(null)
    setCopiedTurn(null)
    setQuestion("")
    setInspectedTurn(null)
    setHighlightedRank(null)
    setHighlightedUnit(null)
    setActiveTab("sources")
  }

  function openResearch(id: string) {
    library.openSession(id)
    setNoteLink(null)
    setCopiedTurn(null)
    setQuestion("")
    setInspectedTurn(null)
    setHighlightedRank(null)
    setHighlightedUnit(null)
    setActiveTab("sources")
    setExportError("")
  }

  const [notifyPermission, setNotifyPermission] = useState(() => typeof Notification === "undefined" ? "unsupported" : Notification.permission)

  async function askToNotify() {
    try { setNotifyPermission(await Notification.requestPermission()) } catch { setNotifyPermission("denied") }
  }

  function cancel() {
    cancelRun(library.active.id)
  }

  function removeResearch(id: string) {
    cancelRun(id)
    library.remove(id)
    if (id === library.active.id) { setInspectedTurn(null); setHighlightedRank(null); setHighlightedUnit(null); setActiveTab("sources") }
  }

  const openRef = useRef(openResearch)
  useEffect(() => { openRef.current = openResearch })
  useEffect(() => {
    const listener = (event: Event) => openRef.current((event as CustomEvent<string>).detail)
    window.addEventListener(OPEN_RESEARCH_EVENT, listener)
    return () => window.removeEventListener(OPEN_RESEARCH_EVENT, listener)
  }, [])

  function focusSource(rank: number, supportId: string | null = null) {
    setInspectorOpen(true)
    setSelectionVersion((value) => value + 1)
    setActiveTab("sources")
    setHighlightedRank(rank)
    setHighlightedUnit(supportId)
  }

  useEffect(() => {
    if (inspectorOpen && highlightedRank !== null) {
      const source = sourceRefs.current.get(highlightedRank)
      const passage = Array.from(source?.querySelectorAll<HTMLElement>("[data-support-id]") ?? [])
        .find((element) => element.dataset.supportId === highlightedUnit)
      ;(passage ?? source)?.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }, [inspectorOpen, highlightedRank, highlightedUnit, inspectedTurn, selectionVersion])

  function changeMode(next: "research" | "inspect") {
    setMode(next)
    setInspectorOpen(next === "inspect")
    if (next === "research") setActiveTab("sources")
  }

  useRegisterWorkspaceCommands([
    { id: "research-history", label: "Open research history", icon: History, run: () => setHistoryOpen(true) },
    { id: "research-new", label: "New research", icon: MessageSquarePlus, run: newChat },
    { id: "research-export", label: "Export research as Markdown", icon: Download, disabled: Boolean(current?.streaming) || (!turns.some((turn) => !turn.streaming) && !library.active.notes.length), run: exportResearch },
    { id: "research-pinned", label: "Open pinned evidence", icon: Pin, run: () => { setActiveTab("pinned"); setInspectorOpen(true) } },
    { id: "research-compare", label: "Compare pinned evidence", hint: "Select two passages", icon: Columns2, run: () => { setActiveTab("pinned"); setInspectorOpen(true) } },
    { id: "research-notes", label: "Open research notes", icon: NotebookPen, run: () => { setActiveTab("notes"); setInspectorOpen(true) } },
    ...researchSessionCommands(library, openResearch, false, removeResearch),
  ])

  const citedUnits = citedUnitsByRank(evidenceTurn)

  const perf = evidenceTurn?.report
    ? {
        embed: evidenceTurn.report.stages.find((s) => s.name === "query_embedding")?.duration_ms,
        retrieval: evidenceTurn.report.stages.find((s) => s.name === "hybrid_retrieval")?.duration_ms,
        rerank: evidenceTurn.report.stages.find((s) => s.name === "rerank")?.duration_ms,
      }
    : null
  // Client-observed (real, measured) timings — see the Turn interface's
  // comment for why these aren't backend-reported values.
  const llmMs =
    evidenceTurn?.askStartedAt && evidenceTurn?.lastTokenAt
      ? evidenceTurn.lastTokenAt - evidenceTurn.askStartedAt
      : null
  const groundingMs =
    evidenceTurn?.lastTokenAt && evidenceTurn?.groundingAt ? evidenceTurn.groundingAt - evidenceTurn.lastTokenAt : null
  const totalMs =
    evidenceTurn?.askStartedAt && evidenceTurn?.groundingAt
      ? evidenceTurn.groundingAt - evidenceTurn.askStartedAt
      : (evidenceTurn?.report?.total_duration_ms ?? null)

  const timings: { label: string; value: number | null | undefined; title?: string }[] = [
    { label: "Total", value: totalMs },
    { label: "Embed", value: perf?.embed },
    { label: "Retrieval", value: perf?.retrieval },
    { label: "Rerank", value: perf?.rerank },
    { label: "LLM", value: llmMs, title: "Client-measured: from asking to the last token" },
    { label: "Grounding", value: groundingMs, title: "Client-measured: from the last token to the verdict" },
  ]

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex min-h-14 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-2 sm:px-6">
        <div className="flex items-center gap-3">

          <span className="hidden text-xs text-[var(--color-subtle-foreground)] sm:inline">Workspace</span>
          <div role="group" aria-label="Workspace mode" className="flex rounded-lg bg-[var(--color-surface-hover)] p-0.5">
            {(["research", "inspect"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => changeMode(value)}
                className={cn("rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]", mode === value ? "bg-[var(--color-surface)] text-[var(--color-foreground)] shadow-card" : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]")}>
                {value === "research" ? "Research" : "Inspect"}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1">
        <ResearchHistory open={historyOpen} onOpenChange={setHistoryOpen} sessions={library.sessions} activeId={library.active.id} streaming={false}
          onOpen={openResearch} onNew={newChat} onRename={library.rename} onStar={library.star} onRemove={removeResearch} onUndo={library.undoRemove} removedTitle={library.removed?.title} />
        <button type="button" aria-label="Export research as Markdown" disabled={(!turns.some((turn) => !turn.streaming) && !library.active.notes.length) || Boolean(current?.streaming)} onClick={exportResearch}
          className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40">
          <Download className="h-3.5 w-3.5" /><span className="hidden sm:inline">Export</span>
        </button>
        {organization.projects.length > 0 && <select aria-label="Research project" value={organization.assignments[library.active.id] ?? ""} onChange={(event) => organization.assign(library.active.id, event.target.value || null)} className="h-8 max-w-40 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs"><option value="">No project</option>{organization.projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>}
        <button type="button" aria-label="Compare documents" aria-expanded={compareOpen} onClick={() => setCompareOpen(!compareOpen)} className="rounded-md px-2.5 py-1.5 text-xs hover:bg-[var(--color-surface-hover)]">Compare documents</button>
        <ShareViewButton values={workspaceView.query} />
        <button type="button" aria-label="Open research notes" onClick={() => { setNoteLink(null); setActiveTab("notes"); setInspectorOpen(true) }} className="flex min-h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"><NotebookPen className="h-3.5 w-3.5" /><span className="hidden sm:inline">Notes</span></button>
        <button type="button" aria-label={`Pinned evidence (${library.active.pins.length})`} onClick={() => { setActiveTab("pinned"); setInspectorOpen(true) }}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
          <Pin className="h-3.5 w-3.5" />{library.active.pins.length}
        </button>
        <button type="button" aria-expanded={inspectorOpen} aria-controls="evidence-inspector" onClick={() => setInspectorOpen(!inspectorOpen)}
          className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-medium text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
          <PanelRight className="h-3.5 w-3.5" /> Evidence
          {evidenceTurn && <span className="font-technical text-[11px] text-[var(--color-subtle-foreground)]">{evidenceTurn.sources.length}</span>}
        </button>
        </div>
      </div>
      {compareOpen && <div className="shrink-0 overflow-y-auto border-b border-[var(--color-border)] p-4" style={{ maxHeight: "45vh" }}><ComparisonComposer disabled={Boolean(current?.streaming)} onCompare={(q, ids) => { setCompareOpen(false); void ask(q, undefined, ids) }} /></div>}
      {(library.storageError || organization.error || exportError) && <p role="status" className="border-b border-[var(--color-border)] px-6 py-2 text-xs text-[var(--color-warning)]">{exportError || organization.error || "Browser storage is unavailable or full. This research is available for this visit; export it to keep a copy."}</p>}
      {background.length > 0 && (
        <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--color-border)] px-6 py-2 text-xs text-[var(--color-muted-foreground)]">
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" aria-hidden />{background.length === 1 ? "1 research is" : `${background.length} researches are`} still running</span>
          {background.map((run) => (
            <button key={run.sessionId} type="button" onClick={() => openResearch(run.sessionId)} className="max-w-64 truncate rounded px-1.5 py-0.5 text-[var(--color-foreground)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" title={run.question}>{run.question}</button>
          ))}
        </div>
      )}
      {turns.length > 0 && <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-6 py-2 text-xs text-[var(--color-subtle-foreground)]"><span className="truncate" title={library.active.title}>{library.active.customTitle ? library.active.title : "Research session"}</span><span className="ml-auto shrink-0">Local research</span></div>}
      <div className="flex min-h-0 flex-1 overflow-hidden">
      {/* Conversation */}
      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-5 py-10 sm:px-10">
            {turns.length === 0 ? (
              <div className="animate-in my-auto flex flex-col items-start gap-5 py-8">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-accent)]">
                  <Sparkles className="h-6 w-6" strokeWidth={1.75} />
                </span>
                <div>
                  <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--color-subtle-foreground)]">Your knowledge, connected</p>
                  <h2 className="max-w-lg text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">A clearer answer.<br /><span className="text-[var(--color-muted-foreground)]">Evidence you can explore.</span></h2>
                </div>
                <p className="max-w-md text-sm text-[var(--color-muted-foreground)]">
                  Ask a question across your documents. Follow each citation to its source, then explore how the answer came together.
                </p>
                <div className="mt-3 grid w-full gap-0 border-y border-[var(--color-border)] sm:grid-cols-3">
                  {[
                    { icon: Search, title: "Ask a question", detail: "Search your connected knowledge" },
                    { icon: FileText, title: "Follow the evidence", detail: "Read the passages behind an answer" },
                    { icon: BookOpen, title: "Go a little deeper", detail: "Inspect retrieval and validation" },
                  ].map(({ icon: Icon, title, detail }) => (
                    <div key={title} className="flex flex-col gap-2 py-5 pr-4">
                      <Icon className="h-4 w-4 text-[var(--color-subtle-foreground)]" strokeWidth={1.5} />
                      <span className="text-xs font-medium">{title}</span>
                      <span className="text-xs leading-relaxed text-[var(--color-muted-foreground)]">{detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-8">
                {turns.map((turn, i) => (
                  <div key={i} className="animate-in flex flex-col gap-4">
                    <div className="flex flex-col items-start gap-2 border-b border-[var(--color-border)] pb-5">
                      <div className="whitespace-pre-wrap text-xl font-semibold leading-relaxed tracking-tight text-[var(--color-foreground)]">
                        {turn.question}
                      </div>
                      {turn.clarificationReply && <p className="text-xs text-[var(--color-muted-foreground)]">Clarification: {turn.clarificationReply.answer}</p>}
                      {searchedAs(turn.report) && (
                        <div className="text-xs text-[var(--color-subtle-foreground)]">
                          Searched as: {searchedAs(turn.report)}
                        </div>
                      )}
                    </div>

                    <div className="flex gap-3">
                      <span
                        aria-hidden="true"
                        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-accent)] shadow-card"
                      >
                        <Sparkles className="h-3.5 w-3.5" strokeWidth={2} />
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col gap-3">
                        <ResearchActivity steps={turn.steps ?? []} streaming={turn.streaming} startedAt={turn.researchStartedAt} finishedAt={turn.researchFinishedAt} outcome={researchOutcome(turn)} />
                        {turn.clarification && <ClarificationPrompt clarification={turn.clarification} disabled={Boolean(current?.streaming) || i !== turns.length - 1} onReply={(answer) => void ask(turn.question, { question: turn.clarification!.question, answer }, turn.sourceIds, turn.metadata?.trace_id)} />}
                        <div className="text-[15px] leading-7 text-[var(--color-foreground)]">
                          {turn.errorMessage && turn.answer === "" ? (
                            <span className="text-[var(--color-error)]">{turn.errorMessage}</span>
                          ) : turn.streaming && turn.answer === "" ? (
                            <span className="inline-flex items-center gap-1 py-1.5" aria-label="Thinking">
                              {[0, 150, 300].map((delay) => (
                                <span
                                  key={delay}
                                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-subtle-foreground)]"
                                  style={{ animationDelay: `${delay}ms` }}
                                />
                              ))}
                            </span>
                          ) : (
                            <>
                              {turn.comparison?.length ? <ComparisonTable rows={turn.comparison} sources={turn.sources} units={turn.metadata?.support_units ?? []} onCite={(rank, supportId) => { setInspectedTurn(i); focusSource(rank, supportId) }} /> : <AnswerBody
                                answer={turn.answer}
                                sources={turn.sources}
                                supportUnits={turn.metadata?.support_units ?? []}
                                onCite={(rank, supportId) => { setInspectedTurn(i); focusSource(rank, supportId) }}
                              />}
                              {turn.streaming && (
                                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-[var(--color-accent)]" />
                              )}
                            </>
                          )}
                        </div>
                        {calculationsOf(turn).map((calculation) => (
                          <CalculationCard key={calculation.id} calculation={calculation} units={turn.metadata?.support_units ?? []}
                            onCite={(rank, supportId) => { setInspectedTurn(i); focusSource(rank, supportId) }} />
                        ))}
                        {!turn.streaming && turn.sources.length > 0 && (
                          <button type="button" aria-controls="evidence-inspector" aria-expanded={inspectorOpen && activeTab === "sources" && (inspectedTurn ?? turns.length - 1) === i} onClick={() => { setInspectedTurn(i); const citation = segmentsOf(turn).find((segment) => segment.type === "citation" && segment.valid && segment.source); focusSource(citation?.source?.rank ?? turn.sources[0].rank, citation?.unit?.support_id ?? null) }}
                            className="flex w-fit items-center gap-2 rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-xs text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
                            <FileText className="h-3.5 w-3.5" /> Supporting evidence <span className="font-technical">{turn.sources.length}</span>
                          </button>
                        )}
                        {!turn.streaming && i === turns.length - 1 && followUpsOf(turn).length > 0 && (
                          <div aria-label="Suggested follow-up questions" className="flex flex-wrap gap-2">
                            {followUpsOf(turn).map((text) => (
                              <button key={text} type="button" onClick={() => { setQuestion(text); requestAnimationFrame(() => { const el = composerRef.current; if (el) { el.focus(); fitComposer(el) } }) }}
                                className="rounded-full border border-[var(--color-border)] px-3 py-1 text-left text-xs text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
                                {text}
                              </button>
                            ))}
                          </div>
                        )}
                        {!turn.streaming && turn.answer && <AnswerFeedback turn={turn} />}
                        {!turn.streaming && turn.answer && (
                          <div className="flex items-start justify-between gap-2">
                            {statusOf(turn) ? <AnswerStatusLine status={statusOf(turn)!} /> : <span />}
                            <span className="flex shrink-0 items-center gap-1">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  onClick={() => void shareReport(i, turn)}
                                  aria-label={sharingTurn === i ? "Preparing report" : "Download shareable report"}
                                  disabled={sharingTurn === i}
                                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-subtle-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-50"
                                >
                                  <Share2 className="h-3.5 w-3.5" />
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>Download a shareable report with sources and pages</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  onClick={() => copyAnswer(i, turn.answer)}
                                  aria-label={copiedTurn === i ? "Copied" : "Copy answer"}
                                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-subtle-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                                >
                                  {copiedTurn === i ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>{copiedTurn === i ? "Copied" : "Copy answer"}</TooltipContent>
                            </Tooltip>
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="px-4 pb-4 pt-3 sm:px-8 sm:pb-6">
          <div className="mx-auto w-full max-w-3xl">
            <div className="rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-card transition-colors focus-within:border-[var(--color-border-strong)]">
              <textarea
                ref={composerRef}
                rows={1}
                aria-label="Question"
                className="block max-h-48 w-full resize-none bg-transparent px-4 pt-3.5 text-sm text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-subtle-foreground)]"
                placeholder="Ask anything…"
                value={question}
                onChange={(e) => {
                  setQuestion(e.target.value)
                  fitComposer(e.target)
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    void ask()
                  }
                }}
                disabled={current?.streaming}
              />
              <div className="flex items-center gap-2 px-2.5 pb-2.5 pt-1.5">
                <button
                  type="button"
                  onClick={newChat}
                  disabled={turns.length === 0 && library.active.notes.length === 0}
                  className="flex h-7 items-center gap-1.5 whitespace-nowrap rounded-lg px-2 text-xs font-medium text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] disabled:pointer-events-none disabled:opacity-40"
                  aria-label="New chat"
                  title="New chat"
                >
                  <MessageSquarePlus className="h-3.5 w-3.5" />
                  New chat
                </button>
                <CoverageBadge />
                <span className="ml-auto hidden truncate text-[11px] text-[var(--color-subtle-foreground)] lg:inline">
                  Enter to ask · Shift+Enter for a new line
                </span>
                {current?.streaming && notifyPermission === "default" && (
                  <button type="button" onClick={askToNotify} title="Get a browser notification when this research finishes in another tab"
                    className="flex h-7 items-center gap-1.5 whitespace-nowrap rounded-lg px-2 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]">
                    <Bell className="h-3.5 w-3.5" /> Notify me
                  </button>
                )}
                {current?.streaming ? (
                  <button
                    type="button"
                    onClick={cancel}
                    className="ml-auto flex h-8 lg:ml-0 w-8 items-center justify-center rounded-lg bg-[var(--color-error-muted)] text-[var(--color-error)] transition-colors hover:opacity-90"
                    aria-label="Cancel"
                  >
                    <Square className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void ask()}
                    disabled={!question.trim()}
                    className="ml-auto flex h-8 lg:ml-0 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-foreground)] shadow-card transition-[opacity,transform] hover:opacity-90 active:scale-95 disabled:opacity-30"
                    aria-label="Ask"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Evidence inspector */}
      <InspectorPanel preferencesKey={`${researchScope(identity)}:panel-width`} open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
          <div className="shrink-0 border-b border-[var(--color-border)] px-3 py-2.5">
            <TabsList className="grid w-full grid-cols-4 [&>button]:min-w-0 [&>button]:px-2 [&>button]:py-1.5 [&>button]:text-xs">
              <TabsTrigger value="sources">Sources</TabsTrigger>
              <TabsTrigger value="pinned">Pinned</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="why">Why</TabsTrigger>
              {mode === "inspect" && <>
                <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
                <TabsTrigger value="security">Security</TabsTrigger>
                <TabsTrigger value="trace">Trace</TabsTrigger>
              </>}
            </TabsList>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
              <TabsContent value="sources">
                {!evidenceTurn || evidenceTurn.sources.length === 0 ? (
                  <EmptyState title="No sources yet" description="Ask a question to see the retrieved evidence." />
                ) : (
                  <EvidenceSources key={`${library.active.id}:${inspectedTurn ?? turns.length - 1}:${selectionVersion}`} sources={evidenceTurn.sources} units={citedUnits} answer={evidenceTurn.answer} supportUnits={evidenceTurn.metadata?.support_units ?? []}
                    highlightedRank={highlightedRank} highlightedUnit={highlightedUnit} technical={mode === "inspect"}
                    citedRanks={new Set(evidenceTurn.sources.filter((source) => evidenceTurn.grounding?.citations_found.some(([, sid]) => sid === source.source_id)).map((source) => source.rank))}
                    cardRef={(rank, el) => { if (el) sourceRefs.current.set(rank, el); else sourceRefs.current.delete(rank) }}
                    onPin={!evidenceTurn.streaming ? (rank, supportId) => library.togglePin({ turnIndex: inspectedTurn ?? turns.length - 1, sourceRank: rank, supportId }) : undefined}
                    isPinned={(rank, supportId) => library.active.pins.some((pin) => samePin(pin, { turnIndex: inspectedTurn ?? turns.length - 1, sourceRank: rank, supportId }))} />
                )}
              </TabsContent>
              <TabsContent value="pinned">
                <PinnedEvidence key={library.active.id} session={library.active} onRemove={library.togglePin} onAddNote={(pin) => { setNoteLink(pin); setActiveTab("notes") }} onOpen={(pin) => { setInspectedTurn(pin.turnIndex); focusSource(pin.sourceRank, pin.supportId) }} />
              </TabsContent>
              <TabsContent value="notes">
                <ResearchNotes key={library.active.id} session={library.active} initialEvidence={noteLink} disabled={Boolean(current?.streaming)} onSave={library.saveNote} onRemove={library.removeNote} onOpen={(pin) => { setInspectedTurn(pin.turnIndex); focusSource(pin.sourceRank, pin.supportId) }} />
              </TabsContent>
              <TabsContent value="why">
                {!evidenceTurn ? (
                  <EmptyState title="Nothing to explain yet" description="Ask a question to see how the answer was made." />
                ) : (
                  <WhyPanel
                    question={evidenceTurn.question}
                    report={evidenceTurn.report}
                    sources={evidenceTurn.sources}
                    metadata={evidenceTurn.metadata}
                    validation={evidenceTurn.validation}
                    status={statusOf(evidenceTurn)}
                  />
                )}
              </TabsContent>
              <TabsContent value="retrieval">
                {!evidenceTurn?.report ? (
                  <EmptyState title="No retrieval data yet" />
                ) : (
                  <RetrievalPipeline report={evidenceTurn.report} />
                )}
              </TabsContent>
              <TabsContent value="security">
                <SecurityInspector report={evidenceTurn?.report ?? null} identity={identity} />
              </TabsContent>
              <TabsContent value="trace">
                {!evidenceTurn?.metadata?.trace_id ? (
                  <EmptyState title="No trace yet" />
                ) : traceQuery.data ? (
                  <TraceWaterfall trace={traceQuery.data} />
                ) : (
                  <EmptyState title="Loading trace…" description="Jaeger ingestion is asynchronous." />
                )}
              </TabsContent>
          </div>

          {/* Performance strip */}
          {mode === "inspect" && <dl className="grid shrink-0 grid-cols-3 gap-px border-t border-[var(--color-border)] bg-[var(--color-border)]">
            {timings.map(({ label, value, title }) => (
              <div key={label} title={title} className="bg-[var(--color-surface)] px-4 py-2">
                <dt className="text-[11px] text-[var(--color-subtle-foreground)]">{label}</dt>
                <dd className="font-technical text-xs text-[var(--color-foreground)]">{formatMs(value)}</dd>
              </div>
            ))}
          </dl>}
        </Tabs>
      </InspectorPanel>
      </div>
    </div>
  )
}
