import { api } from "@/api/client"
import type { HealthStatus, Identity, ReadinessCheck } from "@/api/types"

export const healthApi = {
  liveness: () => api.get<HealthStatus>("/health"),
  readiness: () => api.get<ReadinessCheck>("/health/ready"),
}

export const authApi = {
  identity: () => api.get<Identity>("/ui/identity"),
}
