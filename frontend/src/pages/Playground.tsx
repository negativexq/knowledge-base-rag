import { useEffect, useRef, useState } from "react"
import { ArrowUp, Check, Copy, MessageSquarePlus, Sparkles, Square } from "lucide-react"

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
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
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
    requestAnimationFrame(() => fitComposer(composerRef.current))
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

  // The composer grows with its text up to its max height, then scrolls.
  function fitComposer(el: HTMLTextAreaElement | null) {
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
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

  const timings: { label: string; value: number | null | undefined; title?: string }[] = [
    { label: "Total", value: totalMs },
    { label: "Embed", value: perf?.embed },
    { label: "Retrieval", value: perf?.retrieval },
    { label: "Rerank", value: perf?.rerank },
    { label: "LLM", value: llmMs, title: "Client-measured: from asking to the last token" },
    { label: "Grounding", value: groundingMs, title: "Client-measured: from the last token to the verdict" },
  ]

  return (
    <div className="flex h-full overflow-hidden">
      {/* Conversation */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-6 py-8">
            {turns.length === 0 ? (
              <div className="animate-in my-auto flex flex-col items-center gap-3 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-accent)] text-[var(--color-accent-foreground)] shadow-pop">
                  <Sparkles className="h-6 w-6" strokeWidth={1.75} />
                </span>
                <h2 className="text-xl font-semibold tracking-tight">Ask anything about the ingested documents</h2>
                <p className="max-w-md text-sm text-[var(--color-muted-foreground)]">
                  Answers cite the passages they rest on; hover a citation to read it, and open{" "}
                  <span className="font-medium text-[var(--color-foreground)]">Why</span> to see how the answer was made.
                </p>
                <p className="font-technical text-xs text-[var(--color-subtle-foreground)]">
                  Retrieving as {identity?.tenant_id ?? "…"} ({identity?.roles.join(", ") ?? "…"})
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-8">
                {turns.map((turn, i) => (
                  <div key={i} className="animate-in flex flex-col gap-4">
                    <div className="ml-auto flex max-w-[85%] flex-col items-end gap-1">
                      <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-[var(--color-accent-muted)] px-4 py-2.5 text-sm text-[var(--color-foreground)]">
                        {turn.question}
                      </div>
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
                        <div className="text-sm leading-relaxed text-[var(--color-foreground)]">
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
                              <AnswerBody
                                answer={turn.answer}
                                sources={turn.sources}
                                supportUnits={turn.metadata?.support_units ?? []}
                                onCite={focusSource}
                              />
                              {turn.streaming && (
                                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-[var(--color-accent)]" />
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
                                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-subtle-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                                >
                                  {copiedTurn === i ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>{copiedTurn === i ? "Copied" : "Copy answer"}</TooltipContent>
                            </Tooltip>
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

        <div className="px-6 pb-5">
          <div className="mx-auto w-full max-w-3xl">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-pop transition-colors focus-within:border-[var(--color-border-strong)]">
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
                  disabled={turns.length === 0}
                  className="flex h-7 items-center gap-1.5 whitespace-nowrap rounded-lg px-2 text-xs font-medium text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)] disabled:pointer-events-none disabled:opacity-40"
                  aria-label="New chat"
                  title="New chat"
                >
                  <MessageSquarePlus className="h-3.5 w-3.5" />
                  New chat
                </button>
                <span className="ml-auto hidden truncate text-[11px] text-[var(--color-subtle-foreground)] lg:inline">
                  Enter to ask · Shift+Enter for a new line
                </span>
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
      <aside className="flex w-[min(500px,46%)] shrink-0 flex-col overflow-hidden border-l border-[var(--color-border)] bg-[var(--color-surface)]">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
          <div className="flex items-center gap-2 overflow-x-auto border-b border-[var(--color-border)] px-4 py-2.5">
            <TabsList>
              <TabsTrigger value="sources">Sources</TabsTrigger>
              <TabsTrigger value="why">Why</TabsTrigger>
              <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
              <TabsTrigger value="security">Security</TabsTrigger>
              <TabsTrigger value="trace">Trace</TabsTrigger>
            </TabsList>
          </div>
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

          {/* Performance strip */}
          <dl className="grid shrink-0 grid-cols-3 gap-px border-t border-[var(--color-border)] bg-[var(--color-border)]">
            {timings.map(({ label, value, title }) => (
              <div key={label} title={title} className="bg-[var(--color-surface)] px-4 py-2">
                <dt className="text-[11px] text-[var(--color-subtle-foreground)]">{label}</dt>
                <dd className="font-technical text-xs text-[var(--color-foreground)]">{formatMs(value)}</dd>
              </div>
            ))}
          </dl>
        </Tabs>
      </aside>
    </div>
  )
}
