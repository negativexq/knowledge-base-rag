import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { useState } from "react"

import { classifyError } from "@/api/client"
import { syncApi } from "@/api/sync"
import { uiApi } from "@/api/ui"
import { EmptyState } from "@/components/EmptyState"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { StatusBadge } from "@/components/StatusBadge"
import { TraceWaterfall } from "@/components/TraceWaterfall"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatRelativeTime } from "@/lib/utils"

export default function Traces() {
  const [params] = useSearchParams()
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(params.get("trace"))
  const [offset, setOffset] = useState(0)
  const chats = useQuery({ queryKey: ["chat-traces", offset], queryFn: () => uiApi.chatTraces(offset), refetchInterval: 5000 })
  const [statusFilter, setStatusFilter] = useState<string>("all")

  const runs = useQuery({ queryKey: ["sync-runs"], queryFn: () => syncApi.allRuns(50) })
  const trace = useQuery({
    queryKey: ["trace", selectedTraceId],
    queryFn: () => uiApi.trace(selectedTraceId!),
    enabled: Boolean(selectedTraceId),
    refetchInterval: (query) => query.state.data?.available ? false : 2000,
  })

  const tracedRuns = (runs.data ?? []).filter((r) => r.trace_id)
  const filtered =
    statusFilter === "all" ? tracedRuns : tracedRuns.filter((r) => r.status === statusFilter)
  const statuses = Array.from(new Set(tracedRuns.map((r) => r.status)))

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div className="flex items-center justify-end">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-xs text-[var(--color-foreground)] outline-none"
        >
          <option value="all">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <p className="text-xs text-[var(--color-muted-foreground)]">
        Chat traces contain operational metadata only. Users see their own requests; operators can inspect requests within their tenant.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent traces</CardTitle>
          </CardHeader>
          <CardContent>
            <h2 className="mb-2 text-xs font-medium">Research requests</h2>
            {chats.isLoading && <LoadingRows rows={3} />}
            {chats.isError && <p role="alert" className="text-xs">Chat traces could not be loaded. <button onClick={() => void chats.refetch()}>Retry</button></p>}
            {chats.data?.length === 0 && <p className="mb-3 text-xs">No recorded research requests.</p>}
            <ul aria-label="Research traces" className="mb-3 space-y-1">{chats.data?.map((request) => <li key={request.trace_id}><button onClick={() => setSelectedTraceId(request.trace_id)} className="flex w-full items-start justify-between gap-2 rounded border border-[var(--color-border)] p-2 text-left text-xs hover:bg-[var(--color-surface-hover)]"><span className="min-w-0"><span className="block truncate">{request.pipeline}</span><span className="block">{formatRelativeTime(request.started_at)}</span><span className="block truncate font-technical">{request.trace_id}</span></span><span>{request.outcome}</span></button></li>)}</ul>
            <div className="mb-4 flex gap-3 text-xs"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><button disabled={chats.data?.length !== 50} onClick={() => setOffset(offset + 50)}>Next</button></div>
            <h2 className="mb-2 text-xs font-medium">Sync requests</h2>
            {runs.isLoading ? <LoadingRows rows={3} /> : runs.isError ? (
              <ErrorState kind={classifyError(runs.error)} detail={(runs.error as Error).message} />
            ) : filtered.length === 0 ? (
              <EmptyState title="No traced sync runs yet" />
            ) : (
              <ul className="flex flex-col gap-1">
                {filtered.map((run) => (
                  <li key={run.id}>
                    <button
                      onClick={() => setSelectedTraceId(run.trace_id)}
                      className={`flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs hover:bg-[var(--color-surface-hover)] ${
                        selectedTraceId === run.trace_id ? "bg-[var(--color-accent-muted)]" : ""
                      }`}
                    >
                      <div>
                        <div className="font-technical capitalize text-[var(--color-foreground)]">
                          sync · {run.source_type}
                        </div>
                        <div className="text-[var(--color-subtle-foreground)]">
                          {formatRelativeTime(run.started_at)}
                        </div>
                      </div>
                      <StatusBadge status={run.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Waterfall</CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedTraceId ? (
              <EmptyState title="Select a trace" description="Choose a trace on the left to see its span waterfall." />
            ) : trace.isError ? (
              <ErrorState kind={classifyError(trace.error)} detail={(trace.error as Error).message} />
            ) : trace.data ? (
              <TraceWaterfall trace={trace.data} />
            ) : (
              <LoadingRows rows={3} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
