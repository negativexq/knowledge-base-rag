import { createContext, useContext, useEffect, useSyncExternalStore } from "react"
import type { ResearchSession } from "@/lib/research"
import type { LucideIcon } from "lucide-react"

export interface WorkspaceCommand { id: string; label: string; hint?: string; icon: LucideIcon; disabled?: boolean; run: () => void; conversation?: { session: ResearchSession; active: boolean; rename: (title: string) => void; star: () => void; pin: () => void; remove: () => void; restore: () => void } }
const empty: WorkspaceCommand[] = []
export function createWorkspaceCommandStore() {
  let snapshot = empty
  const listeners = new Set<() => void>()
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } },
    register: (commands: WorkspaceCommand[]) => {
      snapshot = commands
      listeners.forEach((listener) => listener())
      return () => { if (snapshot === commands) { snapshot = empty; listeners.forEach((listener) => listener()) } }
    },
  }
}
export const WorkspaceCommandsContext = createContext<ReturnType<typeof createWorkspaceCommandStore> | null>(null)
export function useRegisterWorkspaceCommands(commands: WorkspaceCommand[]) {
  const store = useContext(WorkspaceCommandsContext)
  useEffect(() => store?.register(commands), [store, commands])
}
const noSubscribe = () => () => {}
export function useWorkspaceCommands() {
  const store = useContext(WorkspaceCommandsContext)
  return useSyncExternalStore(store?.subscribe ?? noSubscribe, store?.getSnapshot ?? (() => empty), () => empty)
}
