import { useEffect, useState } from "react"
import { fetchPagePreview } from "@/api/research"

// The cited page as the original PDF renders it, pinned to the cited version.
export function PagePreview({ sourceId, documentVersion, page, highlight }: {
  sourceId: string
  documentVersion: string
  page: number
  highlight?: string
}) {
  const [state, setState] = useState<{ url: string; found: boolean } | "loading" | "error">("loading")
  useEffect(() => {
    const controller = new AbortController()
    let url: string | null = null
    fetchPagePreview({ source_type: "filesystem", source_id: sourceId, document_version: documentVersion, page, highlight }, controller.signal)
      .then((result) => { url = result.url; setState(result) })
      .catch(() => { if (!controller.signal.aborted) setState("error") })
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [sourceId, documentVersion, page, highlight])

  if (state === "loading") return <p className="mt-3 text-xs text-[var(--color-muted-foreground)]">Loading page {page}…</p>
  if (state === "error") return <p className="mt-3 text-xs text-[var(--color-muted-foreground)]">The original page is not available for this version.</p>
  return <figure className="mt-3">
    <img src={state.url} alt={`Page ${page} of ${sourceId}`} className="w-full rounded border border-[var(--color-border)] bg-white" />
    <figcaption className="mt-1.5 text-[11px] text-[var(--color-muted-foreground)]">
      {state.found ? "The cited text is highlighted on the original page." : "The cited text could not be located on the page image, so the whole page is shown."}
    </figcaption>
  </figure>
}
