import { useEffect, useRef, useState } from "react"
import { Check, Link } from "lucide-react"
import { viewLink } from "@/lib/viewState"

export function ShareViewButton({ values }: { values: Record<string, string | null> }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle")
  const [link, setLink] = useState("")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current !== null) clearTimeout(timer.current) }, [])
  const currentLink = viewLink(values)
  const copied = state === "copied" && link === currentLink
  async function copy() {
    const url = viewLink(values)
    setLink(url)
    if (timer.current !== null) clearTimeout(timer.current)
    try {
      await navigator.clipboard.writeText(url)
      setState("copied")
      timer.current = setTimeout(() => setState("idle"), 2400)
    }
    catch { setState("manual") }
  }
  return <div className="relative inline-flex shrink-0 items-center">
    <button type="button" aria-label="Copy view link" onClick={() => void copy()} className="flex min-h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
      {copied ? <Check className="h-3.5 w-3.5" /> : <Link className="h-3.5 w-3.5" />}<span className="hidden sm:inline">View link</span>
    </button>
    {copied && <span role="status" className="pointer-events-none absolute right-0 top-full z-50 mt-2 whitespace-nowrap rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs text-[var(--color-foreground)] shadow-pop">View link copied</span>}
    {state === "manual" && link === currentLink && <input aria-label="View link to copy" readOnly value={link} onFocus={(event) => event.target.select()} className="absolute right-0 top-full z-50 mt-2 h-9 w-64 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs shadow-pop" />}
  </div>
}
