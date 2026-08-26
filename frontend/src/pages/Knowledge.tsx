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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatRelativeTime } from "@/lib/utils"

function DocumentDetail({ doc, onClose }: { doc: DocumentRecord; onClose: () => void }) {
  return (
    <div className="fixed inset-y-0 right-0 z-20 w-96 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-xl">
      <button
        onClick={onClose}
        className="mb-4 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
      >
        ← Close
      </button>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-[var(--color-foreground)]">
        <FileText className="h-4 w-4" />
        {doc.source_id}
      </h3>
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
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between gap-2 border-b border-[var(--color-border)] py-1.5">
            <dt className="text-[var(--color-muted-foreground)]">{label}</dt>
            <dd className="truncate font-technical text-[var(--color-foreground)]" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default function Knowledge() {
  const [selectedSourceType, setSelectedSourceType] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null)
  const [search, setSearch] = useState("")

  const sources = useQuery({ queryKey: ["sources"], queryFn: sourcesApi.list })
  const documents = useQuery({
    queryKey: ["documents", selectedSourceType],
    queryFn: () => sourcesApi.documents(selectedSourceType ?? undefined),
    enabled: Boolean(selectedSourceType),
  })

  if (sources.isLoading) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <LoadingRows rows={3} />
      </div>
    )
  }
  if (sources.isError) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <ErrorState kind={classifyError(sources.error)} detail={(sources.error as Error).message} />
      </div>
    )
  }

  const filteredDocs = (documents.data ?? []).filter((d) =>
    d.source_id.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold text-[var(--color-foreground)]">Knowledge Sources</h1>

      {sources.data!.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No sources configured for your tenant"
          description="This tenant has no connectors ingesting documents yet."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {sources.data!.map((source) => (
            <button
              key={source.source_type}
              onClick={() => setSelectedSourceType(source.source_type)}
              className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left transition-colors hover:border-[var(--color-border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
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
      )}

      {selectedSourceType && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="capitalize">{selectedSourceType} documents</CardTitle>
            <input
              placeholder="Filter by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-2 py-1 text-xs text-[var(--color-foreground)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            />
          </CardHeader>
          <CardContent>
            {documents.isLoading ? (
              <LoadingRows rows={4} />
            ) : filteredDocs.length === 0 ? (
              <EmptyState title="No documents match" />
            ) : (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-muted-foreground)]">
                    <th className="py-2 font-medium">Name</th>
                    <th className="py-2 font-medium">Version</th>
                    <th className="py-2 font-medium">Chunks</th>
                    <th className="py-2 font-medium">Status</th>
                    <th className="py-2 font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDocs.map((doc) => (
                    <tr
                      key={doc.source_id}
                      onClick={() => setSelectedDoc(doc)}
                      className="cursor-pointer border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-hover)]"
                    >
                      <td className="py-2 font-technical text-[var(--color-foreground)]">
                        {doc.source_id}
                      </td>
                      <td className="py-2 font-technical text-[var(--color-muted-foreground)]">
                        v{doc.version}
                      </td>
                      <td className="py-2 font-technical text-[var(--color-muted-foreground)]">
                        {doc.chunk_count ?? "—"}
                      </td>
                      <td className="py-2">
                        <StatusBadge status={doc.status} />
                      </td>
                      <td className="py-2 text-[var(--color-subtle-foreground)]">
                        {formatRelativeTime(doc.last_synced_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {selectedDoc && <DocumentDetail doc={selectedDoc} onClose={() => setSelectedDoc(null)} />}
    </div>
  )
}
