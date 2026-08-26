import { api } from "@/api/client"
import type { SyncResult, SyncRun } from "@/api/types"

export const syncApi = {
  trigger: (sourceType: string) => api.post<SyncResult>(`/sync/${encodeURIComponent(sourceType)}`),
  history: (sourceType: string, limit = 50) =>
    api.get<SyncRun[]>(`/sync/${encodeURIComponent(sourceType)}/history?limit=${limit}`),
  // Sprint 24: cross-source-type run listing, scoped server-side to the
  // caller's own tenant (app/api/ui.py::sync_runs) — used by the Sync
  // Runs page's overview table.
  allRuns: (limit = 100) => api.get<SyncRun[]>(`/ui/sync-runs?limit=${limit}`),
}
