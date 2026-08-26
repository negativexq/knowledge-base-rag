import { api } from "@/api/client"
import type { DocumentRecord, SourceSummary } from "@/api/types"

export const sourcesApi = {
  list: () => api.get<SourceSummary[]>("/sources"),
  documents: (sourceType?: string) =>
    api.get<DocumentRecord[]>(
      sourceType ? `/ui/documents?source_type=${encodeURIComponent(sourceType)}` : "/ui/documents",
    ),
}
