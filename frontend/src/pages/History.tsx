import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { IdentityScope } from "@/components/IdentityScope"
import { ResearchHistory } from "@/components/ResearchHistory"
import { useResearchLibrary } from "@/hooks/useResearchLibrary"
import { queueResearch } from "@/lib/organization"
import { researchSessionCommands } from "@/lib/researchCommands"
import { useRegisterWorkspaceCommands } from "@/lib/workspaceCommands"

export default function HistoryPage() { return <IdentityScope>{(scope) => <HistoryWorkspace key={scope} scope={scope} />}</IdentityScope> }
function HistoryWorkspace({ scope }: { scope: string }) {
  const library = useResearchLibrary(scope)
  const navigate = useNavigate()
  const [error, setError] = useState("")
  function open(id: string | null) {
    if (queueResearch(scope, id, null)) navigate("/playground")
    else setError("This browser could not open the conversation. Session storage is unavailable.")
  }
  useRegisterWorkspaceCommands(researchSessionCommands(library, open, false))
  return <div className="mx-auto flex h-full max-w-5xl flex-col gap-3 px-5 py-6 sm:px-8">
    {(library.storageError || error) && <p role="status" className="text-xs text-[var(--color-warning)]">{error || "Browser storage is unavailable or full. Changes may not be retained."}</p>}
    <ResearchHistory embedded sessions={library.sessions} activeId={library.active.id} streaming={false} onOpen={open} onNew={() => open(null)} onRename={library.rename} onStar={library.star} onPin={library.pinSession} onRemove={library.remove} onUndo={library.undoRemove} removedTitle={library.removed?.title} />
  </div>
}
