import { useEffect, useRef, useState } from "react"
import { ArrowUp, Check, Copy, MessageSquarePlus, Square } from "lucide-react"

import { chatApi } from "@/api/chat"
import type {
  AnswerValidation,
  ChatMetadata,
  GroundingResult,
  RetrievalReportPayload,
  RetrievedSource,
  SupportUnitRef,
} from "@/api/types"
import { RetrievalPipeline } from "@/components/RetrievalPipeline"
import { SecurityInspector } from "@/components/SecurityInspector"
import { SourceCard } from "@/components/SourceCard"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TraceWaterfall } from "@/components/TraceWaterfall"
import { useIdentity } from "@/hooks/useIdentity"
import { type AnswerSegment, splitAnswerIntoSegments } from "@/lib/citations"
import { AnswerBody } from "@/components/AnswerBody"
import { AnswerStatusLine } from "@/components/AnswerStatusLine"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WhyPanel } from "@/components/WhyPanel"
import { type AnswerStatus, answerStatus } from "@/lib/answerStatus"
import { formatMs } from "@/lib/utils"
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
      { role: "user" as const, content: turn.question },
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

// The conversation survives a page reload within the tab (sessionStorage,
// per tab, cleared by "New chat"). Only finished turns are kept; storage
// can be unavailable (private mode, blocked site data), so every access is
// guarded and the page works without it.
const CONVERSATION_KEY = "kb-console.playground-conversation"

function loadConversation(): Turn[] {
  try {
    const raw = sessionStorage.getItem(CONVERSATION_KEY)
    return raw ? (JSON.parse(raw) as Turn[]) : []
  } catch {
    return []
  }
}

function saveConversation(turns: Turn[]): void {
  try {
    const finished = turns.filter((turn) => !turn.streaming)
    if (finished.length === 0) sessionStorage.removeItem(CONVERSATION_KEY)
    else sessionStorage.setItem(CONVERSATION_KEY, JSON.stringify(finished))
  } catch {
    // Storage unavailable: the conversation just won't survive a reload.
  }
}

function isAnswerValidation(payload: unknown): payload is AnswerValidation {
  return typeof (payload as { passed?: unknown } | null)?.passed === "boolean"
}

interface Turn {
  question: string
  answer: string
  sources: RetrievedSource[]
  report: RetrievalReportPayload | null
  grounding: GroundingResult | null
  validation: AnswerValidation | null
  metadata: ChatMetadata | null
  streaming: boolean
  errorMessage: string | null
  // Sprint 24: client-observed wall-clock timings — real measured
  // durations (performance.now() deltas between real SSE events this
  // browser received), never a backend-reported value the stream
  // doesn't actually carry. The backend's SSE contract has no per-token
  // or per-check timing, so this is the only honest way to show
  // generation/grounding duration without fabricating it.
  firstTokenAt: number | null
  lastTokenAt: number | null
  groundingAt: number | null
  askStartedAt: number | null
}

export default function Playground() {
  const { data: identity } = useIdentity()
  const [turns, setTurns] = useState<Turn[]>(loadConversation)
  const [copiedTurn, setCopiedTurn] = useState<number | null>(null)
  const [question, setQuestion] = useState("")
  const [activeTab, setActiveTab] = useState("sources")
  const [highlightedRank, setHighlightedRank] = useState<number | null>(null)
  const [highlightedUnit, setHighlightedUnit] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sourceRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  const current = turns[turns.length - 1]

  useEffect(() => saveConversation(turns), [turns])

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
    queryKey: ["trace", current?.metadata?.trace_id],
    queryFn: () => uiApi.trace(current!.metadata!.trace_id),
    enabled: Boolean(current?.metadata?.trace_id) && activeTab === "trace",
    refetchInterval: (query) => (query.state.data?.available ? false : 2000),
  })

  function updateCurrent(patch: Partial<Turn>) {
    setTurns((prev) => {
      const copy = [...prev]
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch }
      return copy
    })
  }

  async function ask() {
    const q = question.trim()
    if (!q || current?.streaming) return
    const history = historyFrom(turns)
    setQuestion("")
    setTurns((prev) => [
      ...prev,
      {
        question: q,
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
      },
    ])
    setActiveTab("sources")
    setHighlightedRank(null)
    setHighlightedUnit(null)

    const controller = new AbortController()
    abortRef.current = controller

    let answerBuffer = ""
    let firstTokenAt: number | null = null
    await chatApi.ask(
      q,
      history,
      {
        onSources: (sources) => updateCurrent({ sources: sources as RetrievedSource[] }),
        onRetrieval: (report) => updateCurrent({ report: report as RetrievalReportPayload }),
        onSecurity: (security) => {
          if (isAnswerValidation(security)) {
            updateCurrent({ validation: security, groundingAt: performance.now() })
          }
          setTurns((prev) => {
            const copy = [...prev]
            const currentTurn = copy[copy.length - 1]
            if (!currentTurn?.report) return prev
            copy[copy.length - 1] = {
              ...currentTurn,
              report: {
                ...currentTurn.report,
                security: { ...currentTurn.report.security, ...(security as object) },
              },
            }
            return copy
          })
        },
        onMetadata: (metadata) => updateCurrent({ metadata: metadata as ChatMetadata }),
        onToken: (token) => {
          if (firstTokenAt === null) firstTokenAt = performance.now()
          answerBuffer += token
          updateCurrent({ answer: answerBuffer, firstTokenAt, lastTokenAt: performance.now() })
        },
        onGrounding: (grounding) =>
          updateCurrent({ grounding: grounding as GroundingResult, groundingAt: performance.now() }),
        onDone: () => updateCurrent({ streaming: false }),
        onError: (message) => updateCurrent({ streaming: false, errorMessage: message }),
      },
      controller.signal,
    )
  }

  function newChat() {
    abortRef.current?.abort()
    setTurns([])
    setHighlightedRank(null)
    setHighlightedUnit(null)
    setActiveTab("sources")
  }

  function cancel() {
    abortRef.current?.abort()
    updateCurrent({ streaming: false, errorMessage: "Cancelled." })
  }

  function focusSource(rank: number, supportId: string | null = null) {
    setActiveTab("sources")
    setHighlightedRank(rank)
    setHighlightedUnit(supportId)
    requestAnimationFrame(() => {
      sourceRefs.current.get(rank)?.scrollIntoView({ behavior: "smooth", block: "center" })
    })
  }

  const citedUnits = citedUnitsByRank(current)

  const perf = current?.report
    ? {
        embed: current.report.stages.find((s) => s.name === "query_embedding")?.duration_ms,
        retrieval: current.report.stages.find((s) => s.name === "hybrid_retrieval")?.duration_ms,
        rerank: current.report.stages.find((s) => s.name === "rerank")?.duration_ms,
      }
    : null
  // Client-observed (real, measured) timings — see the Turn interface's
  // comment for why these aren't backend-reported values.
  const llmMs =
    current?.askStartedAt && current?.lastTokenAt
      ? current.lastTokenAt - current.askStartedAt
      : null
  const groundingMs =
    current?.lastTokenAt && current?.groundingAt ? current.groundingAt - current.lastTokenAt : null
  const totalMs =
    current?.askStartedAt && current?.groundingAt
      ? current.groundingAt - current.askStartedAt
      : (current?.report?.total_duration_ms ?? null)

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 overflow-hidden">
        {/* Conversation — ~55% */}
        <section className="flex w-[55%] flex-col border-r border-[var(--color-border)]">
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {turns.length === 0 ? (
              <EmptyState
                title="Ask anything about the ingested documents"
                description={`Retrieving as ${identity?.tenant_id ?? "…"} (${identity?.roles.join(", ") ?? "…"})`}
              />
            ) : (
              <div className="flex flex-col gap-6">
                {turns.map((turn, i) => (
                  <div key={i} className="flex flex-col gap-3">
                    <div className="ml-auto max-w-[85%] rounded-lg bg-[var(--color-surface-raised)] px-3.5 py-2 text-sm text-[var(--color-foreground)]">
                      {turn.question}
                    </div>
                    {searchedAs(turn.report) && (
                      <div className="ml-auto max-w-[85%] text-xs text-[var(--color-muted-foreground)]">
                        Searched as: {searchedAs(turn.report)}
                      </div>
                    )}
                    <div className="max-w-[95%] text-sm leading-relaxed text-[var(--color-foreground)]">
                      {turn.errorMessage && turn.answer === "" ? (
                        <span className="text-[var(--color-error)]">{turn.errorMessage}</span>
                      ) : (
                        <>
                          <AnswerBody
                            answer={turn.answer}
                            sources={turn.sources}
                            supportUnits={turn.metadata?.support_units ?? []}
                            onCite={focusSource}
                          />
                          {turn.streaming && (
                            <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-[var(--color-accent)]" />
                          )}
                        </>
                      )}
                    </div>
                    {!turn.streaming && turn.answer && (
                      <div className="flex items-start justify-between gap-2">
                        {statusOf(turn) ? <AnswerStatusLine status={statusOf(turn)!} /> : <span />}
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={() => copyAnswer(i, turn.answer)}
                              aria-label={copiedTurn === i ? "Copied" : "Copy answer"}
                              className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--color-subtle-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                            >
                              {copiedTurn === i ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>{copiedTurn === i ? "Copied" : "Copy answer"}</TooltipContent>
                        </Tooltip>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-[var(--color-border)] p-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={newChat}
                disabled={turns.length === 0}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] disabled:opacity-40"
                aria-label="New chat"
                title="New chat"
              >
                <MessageSquarePlus className="h-4 w-4" />
              </button>
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2">
              <input
                className="flex-1 bg-transparent text-sm text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-subtle-foreground)]"
                placeholder="Ask anything…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    void ask()
                  }
                }}
                disabled={current?.streaming}
              />
              {current?.streaming ? (
                <button
                  type="button"
                  onClick={cancel}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-error-muted)] text-[var(--color-error)]"
                  aria-label="Cancel"
                >
                  <Square className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void ask()}
                  disabled={!question.trim()}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-accent)] text-[var(--color-accent-foreground)] disabled:opacity-40"
                  aria-label="Ask"
                >
                  <ArrowUp className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            </div>
          </div>
        </section>

        {/* Evidence Inspector — ~45% */}
        <section className="flex w-[45%] flex-col overflow-hidden">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
            <TabsList>
              <TabsTrigger value="sources">Sources</TabsTrigger>
              <TabsTrigger value="why">Why</TabsTrigger>
              <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
              <TabsTrigger value="security">Security</TabsTrigger>
              <TabsTrigger value="trace">Trace</TabsTrigger>
            </TabsList>
            <div className="flex-1 overflow-y-auto p-4">
              <TabsContent value="sources">
                {!current || current.sources.length === 0 ? (
                  <EmptyState title="No sources yet" description="Ask a question to see the retrieved evidence." />
                ) : (
                  <div className="flex flex-col gap-2">
                    {current.sources.map((source) => (
                      <SourceCard
                        key={source.rank}
                        source={source}
                        cited={
                          (current.grounding?.citations_found.some(
                            ([, sid]) => sid === source.source_id,
                          ) ??
                            false) ||
                          (citedUnits.get(source.rank)?.length ?? 0) > 0
                        }
                        citedUnits={citedUnits.get(source.rank)}
                        highlightedUnitId={highlightedRank === source.rank ? highlightedUnit : null}
                        highlighted={highlightedRank === source.rank}
                        cardRef={(el) => {
                          if (el) sourceRefs.current.set(source.rank, el)
                        }}
                      />
                    ))}
                  </div>
                )}
              </TabsContent>
              <TabsContent value="why">
                {!current ? (
                  <EmptyState title="Nothing to explain yet" description="Ask a question to see how the answer was made." />
                ) : (
                  <WhyPanel
                    question={current.question}
                    report={current.report}
                    sources={current.sources}
                    metadata={current.metadata}
                    validation={current.validation}
                    status={statusOf(current)}
                  />
                )}
              </TabsContent>
              <TabsContent value="retrieval">
                {!current?.report ? (
                  <EmptyState title="No retrieval data yet" />
                ) : (
                  <RetrievalPipeline report={current.report} />
                )}
              </TabsContent>
              <TabsContent value="security">
                <SecurityInspector report={current?.report ?? null} identity={identity} />
              </TabsContent>
              <TabsContent value="trace">
                {!current?.metadata?.trace_id ? (
                  <EmptyState title="No trace yet" />
                ) : traceQuery.data ? (
                  <TraceWaterfall trace={traceQuery.data} />
                ) : (
                  <EmptyState title="Loading trace…" description="Jaeger ingestion is asynchronous." />
                )}
              </TabsContent>
            </div>
          </Tabs>
        </section>
      </div>

      {/* Performance strip */}
      <footer className="flex shrink-0 items-center gap-6 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-2 font-technical text-xs text-[var(--color-muted-foreground)]">
        <span>
          Total <span className="text-[var(--color-foreground)]">{formatMs(totalMs)}</span>
        </span>
        <span>
          Embed <span className="text-[var(--color-foreground)]">{formatMs(perf?.embed)}</span>
        </span>
        <span>
          Retrieval{" "}
          <span className="text-[var(--color-foreground)]">{formatMs(perf?.retrieval)}</span>
        </span>
        <span>
          Rerank <span className="text-[var(--color-foreground)]">{formatMs(perf?.rerank)}</span>
        </span>
        <span>
          LLM (client-measured){" "}
          <span className="text-[var(--color-foreground)]">{formatMs(llmMs)}</span>
        </span>
        <span>
          Grounding (client-measured){" "}
          <span className="text-[var(--color-foreground)]">{formatMs(groundingMs)}</span>
        </span>
      </footer>
    </div>
  )
}
