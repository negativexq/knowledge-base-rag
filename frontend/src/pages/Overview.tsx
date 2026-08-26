import { useQuery } from "@tanstack/react-query"
import { Boxes, Database, FileStack, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react"

import { classifyError } from "@/api/client"
import { healthApi } from "@/api/health"
import { uiApi } from "@/api/ui"
import { EmptyState } from "@/components/EmptyState"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows, LoadingSkeleton } from "@/components/LoadingSkeleton"
import { MetricCard } from "@/components/MetricCard"
import { StatusBadge } from "@/components/StatusBadge"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatRelativeTime } from "@/lib/utils"

export default function Overview() {
  const overview = useQuery({ queryKey: ["overview"], queryFn: uiApi.overview })
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: healthApi.readiness,
    retry: false,
  })

  if (overview.isLoading) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-24" />
          ))}
        </div>
        <LoadingRows rows={4} />
      </div>
    )
  }

  if (overview.isError) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <ErrorState kind={classifyError(overview.error)} detail={(overview.error as Error).message} />
      </div>
    )
  }

  const data = overview.data!

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard label="Documents" value={data.document_count} icon={FileStack} />
        <MetricCard
          label="Chunks"
          value={data.chunk_count_complete ? (data.chunk_count ?? "—") : `${data.chunk_count ?? "—"}+`}
          icon={Boxes}
          caption={data.chunk_count_complete ? undefined : "some documents untracked"}
        />
        <MetricCard label="Sources" value={data.source_count} icon={Database} />
        <MetricCard
          label="Last Sync"
          value={
            data.recent_runs[0] ? formatRelativeTime(data.recent_runs[0].started_at) : "—"
          }
          icon={RefreshCw}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Knowledge Sources</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {data.sources.length === 0 ? (
              <EmptyState title="No sources yet" description="No connectors are configured for your tenant." />
            ) : (
              data.sources.map((source) => (
                <div
                  key={source.source_type}
                  className="flex items-center justify-between rounded-md border border-[var(--color-border)] px-3 py-2.5"
                >
                  <div>
                    <div className="text-sm font-medium capitalize text-[var(--color-foreground)]">
                      {source.source_type}
                    </div>
                    <div className="text-xs text-[var(--color-muted-foreground)]">
                      {source.document_count} documents · last sync{" "}
                      {formatRelativeTime(source.last_sync_at)}
                    </div>
                  </div>
                  <StatusBadge status={source.is_running ? "running" : source.last_sync_status ?? "pending"} />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 font-technical text-xs">
            {readiness.isLoading && <LoadingRows rows={4} />}
            {readiness.isError && (
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-muted-foreground)]">/health/ready</span>
                <StatusBadge status="unavailable" />
              </div>
            )}
            {readiness.data &&
              Object.entries(readiness.data.checks).map(([check, ok]) => (
                <div key={check} className="flex items-center justify-between">
                  <span className="text-[var(--color-muted-foreground)]">{check}</span>
                  <StatusBadge status={ok ? "healthy" : "degraded"} />
                </div>
              ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Syncs</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {data.recent_runs.length === 0 ? (
              <EmptyState title="No sync runs yet" />
            ) : (
              data.recent_runs.slice(0, 5).map((run) => (
                <div key={run.id} className="flex items-center justify-between text-xs">
                  <span className="font-technical text-[var(--color-muted-foreground)]">
                    #{run.id} · {run.source_type}
                  </span>
                  <span className="text-[var(--color-subtle-foreground)]">
                    {formatRelativeTime(run.started_at)}
                  </span>
                  <StatusBadge status={run.status} />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active Index</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
              <span className="font-technical text-[var(--color-foreground)]">
                {data.active_index.model}
              </span>
            </div>
            <div className="pl-4 text-[var(--color-muted-foreground)]">
              {data.active_index.dimension} dimensions
            </div>
            <div className="pl-4 font-technical text-[var(--color-subtle-foreground)]">
              fingerprint {data.active_index.fingerprint.slice(0, 12)}…
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-[var(--color-muted-foreground)]">
              <span>Alias</span>
              <Badge variant="default" className="font-technical">
                {data.active_index.alias}
              </Badge>
              <span>→</span>
              <span className="font-technical">
                {data.active_index.active_collection ?? "not available"}
              </span>
            </div>
            {data.active_index.rollback_available && data.active_index.previous && (
              <div className="mt-1 flex items-center gap-1.5 text-[var(--color-muted-foreground)]">
                <RotateCcw className="h-3 w-3" />
                Rollback available: {data.active_index.previous.model_key}
              </div>
            )}
            {!data.active_index.available && (
              <div className="mt-1 text-[var(--color-subtle-foreground)]">
                Live index state unavailable — showing configured pipeline only.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-success)]" />
              Security
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-y-1.5 text-xs">
            <span className="text-[var(--color-muted-foreground)]">Tenant isolation</span>
            <StatusBadge status={data.security.tenant_isolation ? "enabled" : "disabled"} />
            <span className="text-[var(--color-muted-foreground)]">Mandatory ACL</span>
            <StatusBadge status={data.security.mandatory_acl ? "enabled" : "disabled"} />
            <span className="text-[var(--color-muted-foreground)]">Authentication</span>
            <StatusBadge status={data.security.auth_enabled ? "enabled" : "disabled"} />
            <span className="text-[var(--color-muted-foreground)]">Role</span>
            <span className="font-technical text-[var(--color-foreground)]">
              {data.security.roles.join(", ")}
            </span>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
