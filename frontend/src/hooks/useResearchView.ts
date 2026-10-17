import { useEffect, useState } from "react"
import { readResearchView, researchViewQuery, storedResearchView, updateViewQuery, useViewSearch } from "@/lib/viewState"

export function useResearchView(scope: string) {
  const key = `${scope}:workspace-view`
  const [fallback] = useState(() => storedResearchView(key))
  const view = readResearchView(useViewSearch(), fallback)
  const { mode, tab, open } = view
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify({ mode, tab, open })) }
    catch { /* View controls still work without browser persistence. */ }
  }, [key, mode, tab, open]) // primitive dependencies keep URL-driven updates stable
  return {
    ...view,
    setMode: (mode: "research" | "inspect") => updateViewQuery({ mode }),
    setTab: (tab: string) => updateViewQuery({ panel: tab }),
    setOpen: (open: boolean) => updateViewQuery({ inspector: open ? "open" : "closed" }),
    query: researchViewQuery(view),
  }
}
