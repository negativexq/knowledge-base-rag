import { api } from "@/api/client"
import type { ActiveIndex, Evaluations, Overview, TraceDetail, UiSettings } from "@/api/types"

export const uiApi = {
  overview: () => api.get<Overview>("/ui/overview"),
  activeIndex: () => api.get<ActiveIndex>("/ui/active-index"),
  settings: () => api.get<UiSettings>("/ui/settings"),
  evaluations: () => api.get<Evaluations>("/ui/evaluations"),
  trace: (traceId: string) => api.get<TraceDetail>(`/ui/traces/${encodeURIComponent(traceId)}`),
}
