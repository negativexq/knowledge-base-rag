import { useMemo, useSyncExternalStore } from "react"
import { RESEARCH_EVENT } from "@/lib/organization"
import { readResearchSessions } from "@/lib/research"

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener)
  window.addEventListener(RESEARCH_EVENT, listener)
  return () => { window.removeEventListener("storage", listener); window.removeEventListener(RESEARCH_EVENT, listener) }
}
export function useSavedResearch(scope: string) {
  const snapshot = useSyncExternalStore(subscribe, () => {
    try { return localStorage.getItem(scope) ?? "[]" } catch { return "[]" }
  }, () => "[]")
  return useMemo(() => readResearchSessions(scope, snapshot), [scope, snapshot])
}
