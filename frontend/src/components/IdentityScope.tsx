import type { ReactNode } from "react"
import { classifyError } from "@/api/client"
import { ErrorState } from "@/components/ErrorState"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { useIdentity } from "@/hooks/useIdentity"
import { researchScope } from "@/lib/research"

export function IdentityScope({ children }: { children: (scope: string) => ReactNode }) {
  const identity = useIdentity()
  if (identity.isError) return <div className="p-6"><ErrorState kind={classifyError(identity.error)} detail={(identity.error as Error).message} /></div>
  if (!identity.data) return <div className="p-6"><LoadingRows rows={3} /></div>
  return children(researchScope(identity.data))
}
