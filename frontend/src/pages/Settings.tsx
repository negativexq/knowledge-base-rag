import { useQuery } from "@tanstack/react-query"
import { RotateCcw, ShieldAlert } from "lucide-react"

import { classifyError } from "@/api/client"
import { uiApi } from "@/api/ui"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { StatusBadge } from "@/components/StatusBadge"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useIdentity } from "@/hooks/useIdentity"

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-xs last:border-0">
      <span className="text-[var(--color-muted-foreground)]">{label}</span>
      <span className="font-technical text-[var(--color-foreground)]">{value}</span>
    </div>
  )
}

export default function SettingsPage() {
  const { data: identity } = useIdentity()
  const query = useQuery({ queryKey: ["settings"], queryFn: uiApi.settings })

  if (query.isLoading) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <LoadingRows rows={5} />
      </div>
    )
  }
  if (query.isError) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState kind={classifyError(query.error)} detail={(query.error as Error).message} />
      </div>
    )
  }

  const data = query.data!
  const validationMode = data.security.validation_mode
  const validationModeLabel =
    validationMode === "strict" ? "Strict" : validationMode === "fast" ? "Fast" : validationMode
  const releasePolicy =
    validationMode === "strict"
      ? "Validate before release"
      : validationMode === "fast"
        ? "Post-stream validation"
        : "Not available"

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold text-[var(--color-foreground)]">Settings</h1>
      <p className="text-xs text-[var(--color-muted-foreground)]">
        Read-only view of the active configuration. The console cannot modify backend settings.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Active Pipeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Row label="Active" value={`${data.active_pipeline.model_key}@${data.active_pipeline.output_dimension ?? data.active_pipeline.dimension}`} />
          <Row label="Model" value={data.active_pipeline.model} />
          <Row label="Dimension" value={data.active_pipeline.dimension} />
          <Row label="Fingerprint" value={data.active_pipeline.fingerprint.slice(0, 16) + "…"} />
          <Row label="Alias" value={data.active_pipeline.alias} />
          <Row
            label="Active collection"
            value={data.active_pipeline.active_collection ?? "unavailable"}
          />
          {data.active_pipeline.previous && (
            <Row
              label="Previous"
              value={
                <span className="flex items-center gap-1.5">
                  <RotateCcw className="h-3 w-3" />
                  {data.active_pipeline.previous.model_key}@
                  {data.active_pipeline.previous.output_dimension ?? "native"}
                </span>
              }
            />
          )}
          <Row
            label="Rollback available"
            value={<StatusBadge status={data.active_pipeline.rollback_available ? "enabled" : "disabled"} />}
          />
          {!data.active_pipeline.available && (
            <div className="mt-2 flex items-start gap-2 rounded-md border border-[var(--color-warning)]/30 bg-[var(--color-warning-muted)] p-2">
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-warning)]" />
              <p className="text-[11px] text-[var(--color-muted-foreground)]">
                Live migration/alias state is unavailable — showing configured pipeline only.
              </p>
            </div>
          )}
          <p className="mt-3 text-[11px] text-[var(--color-subtle-foreground)]">
            Rollback is a real, tested backend capability (Sprint 22) but is not exposed as a
            control in this console — it requires ADMIN confirmation and is intentionally kept as
            a CLI operation (<code className="font-technical">scripts/migrate_embedding_index.py rollback</code>).
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retrieval</CardTitle>
        </CardHeader>
        <CardContent>
          <Row label="Candidate k (pre-rerank)" value={data.retrieval.rerank_candidate_k} />
          <Row label="Top n (post-rerank)" value={data.retrieval.rerank_top_n} />
          <Row label="Fusion" value={data.retrieval.fusion} />
          <Row label="Sparse model" value={data.retrieval.sparse_model} />
          <Row label="Reranker enabled" value={data.retrieval.reranker_enabled ? "Yes" : "No"} />
          <Row label="Reranker backend" value={data.retrieval.reranker_backend} />
          <Row label="Reranker model" value={data.retrieval.reranker_model ?? "Not enabled"} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Authentication</CardTitle>
        </CardHeader>
        <CardContent>
          <Row
            label="Enabled"
            value={<StatusBadge status={data.authentication.enabled ? "enabled" : "disabled"} />}
          />
          <Row label="Scheme" value={data.authentication.scheme} />
          <Row label="Roles" value={data.authentication.roles.join(" < ")} />
          <Row label="Current identity" value={`${identity?.user_id} (${identity?.tenant_id})`} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Generation security</CardTitle>
        </CardHeader>
        <CardContent>
          <Row label="Prompt policy" value={data.security.prompt_policy_version} />
          <Row
            label="Retrieved context"
            value={<StatusBadge status={data.security.untrusted_context_enabled ? "enabled" : "disabled"} />}
          />
          <Row label="Validation mode" value={validationModeLabel} />
          <Row label="Release policy" value={releasePolicy} />
          <p className="mt-3 text-[11px] text-[var(--color-subtle-foreground)]">
            Retrieved body and metadata remain untrusted reference data. Authorization is still
            enforced by the backend before retrieval. Validation mode is server-owned and read-only;
            the client cannot downgrade strict enforcement.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Integrations</CardTitle>
        </CardHeader>
        <CardContent>
          <Row label="Qdrant" value={data.integrations.qdrant_url} />
          <Row label="Ollama" value={data.integrations.ollama_base_url} />
          <Row label="OpenTelemetry" value={data.integrations.otel_endpoint} />
          <Row label="Generation provider" value={data.integrations.generation_provider} />
          <Row label="Generation model" value={data.integrations.generation_model} />
        </CardContent>
      </Card>

      {!identity?.is_admin && (
        <Badge className="w-fit">Rollback actions would require ADMIN role</Badge>
      )}
    </div>
  )
}
