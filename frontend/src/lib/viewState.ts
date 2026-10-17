import { useSyncExternalStore } from "react"

const VIEW_EVENT = "kb-console:view-change"
function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback)
  window.addEventListener(VIEW_EVENT, callback)
  return () => { window.removeEventListener("popstate", callback); window.removeEventListener(VIEW_EVENT, callback) }
}
export function useViewSearch(): string {
  return useSyncExternalStore(subscribe, () => window.location.search, () => "")
}

/** Keep router history metadata and unrelated URL parameters intact. */
export function updateViewQuery(patch: Record<string, string | null>): void {
  const url = new URL(window.location.href)
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) url.searchParams.delete(key)
    else url.searchParams.set(key, value)
  }
  if (url.href === window.location.href) return
  window.history.replaceState(window.history.state, "", url)
  window.dispatchEvent(new Event(VIEW_EVENT))
}

/** Share only explicitly allowed view settings, never the current URL wholesale. */
export function viewLink(values: Record<string, string | null>): string {
  const url = new URL(window.location.pathname, window.location.origin)
  for (const [key, value] of Object.entries(values)) if (value !== null) url.searchParams.set(key, value)
  return url.href
}

export const researchTabs = ["sources", "pinned", "notes", "why", "retrieval", "security", "trace"] as const
export interface ResearchView { mode: "research" | "inspect"; tab: string; open: boolean }
const defaultView: ResearchView = { mode: "research", tab: "sources", open: false }
export function readResearchView(search: string, fallback = defaultView): ResearchView {
  const params = new URLSearchParams(search)
  const mode = params.get("mode") === "inspect" ? "inspect" : params.get("mode") === "research" ? "research" : fallback.mode
  const requested = params.get("panel") ?? fallback.tab
  const tab = researchTabs.some((tab) => tab === requested) && (mode === "inspect" || !["retrieval", "security", "trace"].includes(requested)) ? requested : "sources"
  const open = params.get("inspector") === "open" ? true : params.get("inspector") === "closed" ? false : fallback.open
  return { mode, tab, open }
}
export function researchViewQuery(view: ResearchView): Record<string, string> {
  return { mode: view.mode, panel: view.tab, inspector: view.open ? "open" : "closed" }
}

export function storedResearchView(key: string): ResearchView {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null")
    if (value && typeof value.open === "boolean" && ["research", "inspect"].includes(value.mode) && researchTabs.includes(value.tab)) return readResearchView("", value)
  } catch { /* Fall back to the default workspace. */ }
  return defaultView
}
