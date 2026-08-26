import { useQuery } from "@tanstack/react-query"

import { authApi } from "@/api/health"
import { getToken } from "@/api/auth"

export function useIdentity() {
  const token = getToken()
  return useQuery({
    queryKey: ["identity", token],
    queryFn: authApi.identity,
    enabled: Boolean(token),
    retry: false,
    staleTime: 60_000,
  })
}
