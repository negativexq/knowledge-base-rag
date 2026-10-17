import { useState, type ReactNode } from "react"
import { createWorkspaceCommandStore, WorkspaceCommandsContext } from "@/lib/workspaceCommands"

export function WorkspaceCommandsProvider({ children }: { children: ReactNode }) {
  const [store] = useState(createWorkspaceCommandStore)
  return <WorkspaceCommandsContext.Provider value={store}>{children}</WorkspaceCommandsContext.Provider>
}
