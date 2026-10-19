import { DocumentPermissions } from "@/components/DocumentPermissions"
import { DocumentExplorer } from "@/components/DocumentExplorer"
import { useQuery } from "@tanstack/react-query"
import { ChevronRight, Database, FileText } from "lucide-react"
import { useState } from "react"

import { classifyError } from "@/api/client"
import { sourcesApi } from "@/api/sources"
import type { DocumentRecord } from "@/api/types"
import { EmptyState } from "@/components/EmptyState"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { StatusBadge } from "@/components/StatusBadge"
import { KnowledgeDocuments } from "@/components/KnowledgeDocuments"
import { useIdentity } from "@/hooks/useIdentity"
import { updateViewQuery, useViewSearch } from "@/lib/viewState"
import { readKnowledgeView } from "@/lib/knowledgeView"
import { researchScope } from "@/lib/research"
import { Dialog } from "radix-ui"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { qualityRows, qualitySummary } from "@/lib/quality"
import { formatRelativeTime } from "@/lib/utils"

function DocumentDetail({ doc, onClose }: { doc: DocumentRecord; onClose: () => void }) {
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose() }}>
      <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm" />
      <Dialog.Content aria-describedby={undefined} className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop">
      <button
        onClick={onClose}
        className="mb-4 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
      >
        ← Close
      </button>
      <Dialog.Title className="mb-3 flex items-center gap-2 text-sm font-medium text-[var(--color-foreground)]">
        <FileText className="h-4 w-4" />
        {doc.source_id}
      </Dialog.Title>
      <dl className="flex flex-col gap-2 text-xs">
        {[
          ["Source", doc.source_type],
          ["Current version", String(doc.version)],
          ["Content hash", doc.content_hash],
          ["Pipeline fingerprint", doc.pipeline_fingerprint ?? "not tracked"],
          ["Chunk count", doc.chunk_count === null ? "not tracked" : String(doc.chunk_count)],
          ["Indexed at", formatRelativeTime(doc.last_synced_at)],
          ["Status", doc.status],
          ["Tenant", doc.tenant_id],
          ["Parse quality", qualitySummary(doc.ingestion_quality).label],
          ...(doc.ingestion_quality ? qualityRows(doc.ingestion_quality) : []),
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5">
            <dt className="text-[var(--color-muted-foreground)]">{label}</dt>
            <dd className="truncate font-technical text-[var(--color-foreground)]" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <DocumentExplorer document={{ source_type: doc.source_type, source_id: doc.source_id, document_version: doc.content_hash }} />
      </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default function Knowledge() {
  const selectedSourceType = readKnowledgeView(useViewSearch()).source
  const setSelectedSourceType = (source: string) => updateViewQuery({ source, page: null })
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null)
  const { data: identity } = useIdentity()
  const scope = identity ? researchScope(identity) : "unresolved"

  const sources = useQuery({ queryKey: ["sources", scope], queryFn: sourcesApi.list })
  const documents = useQuery({
    queryKey: ["documents", scope, selectedSourceType],
    queryFn: () => sourcesApi.documents(selectedSourceType === "*" ? undefined : selectedSourceType ?? undefined),
    enabled: Boolean(selectedSourceType),
  })

  if (sources.isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <LoadingRows rows={3} />
      </div>
    )
  }
  if (sources.isError) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <ErrorState kind={classifyError(sources.error)} detail={(sources.error as Error).message} />
      </div>
    )
  }


  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      {identity?.is_admin && <DocumentPermissions scope={scope} />}

      {sources.data!.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No sources configured for your tenant"
          description="This tenant has no connectors ingesting documents yet."
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between"><p className="text-xs text-[var(--color-muted-foreground)]">Browse connected knowledge</p><button type="button" onClick={() => setSelectedSourceType("*")} aria-pressed={selectedSourceType === "*"} className="rounded-md px-3 py-2 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-muted)]">All documents</button></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {sources.data!.map((source) => (
            <button
              key={source.source_type}
              onClick={() => { setSelectedSourceType(source.source_type); setSelectedDoc(null) }}
              aria-pressed={selectedSourceType === source.source_type}
              className="flex items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 text-left shadow-card transition-all hover:-translate-y-px hover:border-[var(--color-border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium capitalize text-[var(--color-foreground)]">
                    {source.source_type}
                  </span>
                  <StatusBadge status={source.is_running ? "running" : "healthy"} />
                </div>
                <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
                  {source.document_count} documents
                </p>
              </div>
              <ChevronRight className="h-4 w-4 text-[var(--color-subtle-foreground)]" />
            </button>
          ))}
          </div>
        </div>
      )}

      {selectedSourceType && sources.data!.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="capitalize">{selectedSourceType === "*" ? "All" : selectedSourceType} documents</CardTitle>
          </CardHeader>
          <CardContent>
            {documents.isLoading ? <LoadingRows rows={4} /> : documents.isError ? (
              <div className="space-y-3"><ErrorState kind={classifyError(documents.error)} detail={(documents.error as Error).message} /><button type="button" onClick={() => void documents.refetch()} className="rounded-md border border-[var(--color-border)] px-3 py-2 text-xs">Retry documents</button></div>
            ) : <KnowledgeDocuments key={`${scope}:${selectedSourceType}`} documents={documents.data ?? []} onOpen={setSelectedDoc} preferencesKey={`${scope}:knowledge-table`} organizationScope={identity ? scope : undefined} />}
          </CardContent>
        </Card>
      )}

      {selectedDoc && <DocumentDetail doc={selectedDoc} onClose={() => setSelectedDoc(null)} />}
    </div>
  )
}
