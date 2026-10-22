import type { CalculationSummary, RetrievedSource } from "@/api/types"
import { fetchPagePreview } from "@/api/research"
import { splitAnswerIntoSegments } from "@/lib/citations"
import { researchOutcome, type ResearchTurn } from "@/lib/research"

export interface PageImage { sourceId: string; page: number; dataUrl: string; highlighted: boolean }

interface Reference { id: number; source: RetrievedSource; text: string; supportId?: string; section?: string | null }

const MAX_PAGE_IMAGES = 4

function escape(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!)
}

function outcomeLabel(turn: ResearchTurn): string {
  const outcome = researchOutcome(turn)
  return outcome === "answered" ? "Answer checked against the cited sources"
    : outcome === "unverified" ? "Sufficient evidence could not be verified"
    : "Research stopped before an answer"
}

function calculationHtml(calculation: CalculationSummary, refFor: (supportId: string | null) => number | undefined): string {
  const inputs = calculation.inputs.filter((input) => input.name && input.value !== null).map((input) => {
    const ref = refFor(input.support_id)
    return `<li><code>${escape(input.name)}</code> ${escape(input.label)}: <strong>${escape([input.value, input.unit].filter(Boolean).join(" "))}</strong>${ref ? ` <sup><a href="#ref-${ref}">${ref}</a></sup>` : ""}</li>`
  }).join("")
  const result = escape([calculation.result, calculation.unit].filter(Boolean).join(" "))
  return `<section class="calc"><h3>How this was calculated</h3>${inputs ? `<ul>${inputs}</ul>` : ""}<p><code>${escape(calculation.expression)}</code> = <strong>${result}</strong></p><p class="muted">Computed by the application from the cited values, not by the model.</p></section>`
}

// A self-contained HTML page for one answer: question, cited answer,
// calculation, quoted passages and the cited page images. No scripts.
export function answerReportHtml(turn: ResearchTurn, pages: PageImage[] = [], generatedAt = new Date()): string {
  const segments = splitAnswerIntoSegments(turn.answer, turn.sources, turn.metadata?.support_units ?? [])
  const references = new Map<string, Reference>()
  const body = segments.map((segment) => {
    if (segment.type === "text") return escape(segment.text)
    if (!segment.valid || !segment.source) return `<span class="bad">${escape(segment.text)} (unresolved citation)</span>`
    const key = `${segment.source.rank}:${segment.unit?.support_id ?? "source"}`
    if (!references.has(key)) references.set(key, { id: references.size + 1, source: segment.source, text: segment.unit?.text ?? segment.source.snippet, supportId: segment.unit?.support_id, section: segment.unit?.section_label })
    const id = references.get(key)!.id
    return `<sup><a href="#ref-${id}">${id}</a></sup>`
  }).join("")
  const refFor = (supportId: string | null) => [...references.values()].find((ref) => ref.supportId === supportId)?.id
  const cited = new Set([...references.values()].map((ref) => ref.supportId).filter(Boolean))
  const calculations = researchOutcome(turn) === "answered"
    ? (turn.metadata?.calculations ?? []).filter((calc) => calc.support_ids.some((id) => cited.has(id))) : []
  const referenceHtml = [...references.values()].map((ref) => {
    const location = [ref.source.page_number != null ? `page ${ref.source.page_number}` : null, ref.section, ref.source.document_version ? `version ${ref.source.document_version.slice(0, 12)}` : null].filter(Boolean).join(" · ")
    return `<li id="ref-${ref.id}"><p><strong>${escape(ref.source.source_id ?? "Unknown source")}</strong>${location ? ` <span class="muted">${escape(location)}</span>` : ""}</p><blockquote>${escape(ref.text)}</blockquote></li>`
  }).join("")
  const pageHtml = pages.map((page) => `<figure><img src="${page.dataUrl}" alt="Page ${page.page} of ${escape(page.sourceId)}"><figcaption>${escape(page.sourceId)}, page ${page.page}${page.highlighted ? " · cited text highlighted" : ""}</figcaption></figure>`).join("")
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(turn.question.slice(0, 80))}</title>
<style>
body{font:15px/1.6 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;color:#1d1d1f;background:#fff}
h1{font-size:1.4rem;line-height:1.3}h2{font-size:1.05rem;margin-top:2rem}h3{font-size:.95rem;margin:0 0 .5rem}
.muted{color:#6e6e73;font-size:.85rem}.status{display:inline-block;padding:.15rem .5rem;border-radius:6px;background:#f2f2f4;font-size:.8rem}
.calc{border:1px solid #e3e3e6;border-radius:8px;padding:.75rem 1rem;margin:1rem 0}blockquote{margin:.25rem 0 0;padding-left:.75rem;border-left:3px solid #d2d2d7;white-space:pre-wrap;color:#3a3a3c}
code{font:13px ui-monospace,monospace}.bad{color:#b3261e}figure{margin:1rem 0}img{max-width:100%;border:1px solid #e3e3e6;border-radius:6px}ol{padding-left:1.25rem}
</style></head><body>
<p class="muted">Knowledge Base research report · generated ${escape(generatedAt.toISOString())}</p>
<h1>${escape(turn.question)}</h1>
<p class="status">${escape(outcomeLabel(turn))}</p>
<h2>Answer</h2><p>${body || "No answer returned."}</p>
${calculations.map((calc) => calculationHtml(calc, refFor)).join("")}
${referenceHtml ? `<h2>Cited sources</h2><ol>${referenceHtml}</ol>` : ""}
${pageHtml ? `<h2>Cited pages</h2>${pageHtml}` : ""}
<p class="muted">Quoted passages and page images come from the indexed document versions listed above.</p>
</body></html>
`
}

function toDataUrl(url: string): Promise<string> {
  return fetch(url).then((response) => response.blob()).then((blob) => new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  }))
}

// The cited PDF pages, as images embedded in the report; pages that cannot
// be rendered are left out rather than failing the export.
export async function citedPageImages(turn: ResearchTurn): Promise<PageImage[]> {
  const segments = splitAnswerIntoSegments(turn.answer, turn.sources, turn.metadata?.support_units ?? [])
  const seen = new Set<string>()
  const targets: { source: RetrievedSource; text: string }[] = []
  for (const segment of segments) {
    const source = segment.source
    if (segment.type !== "citation" || !segment.valid || !source || source.source_type !== "filesystem" || source.page_number == null
      || !source.source_id || !/^[0-9a-f]{64}$/.test(source.document_version ?? "")) continue
    const key = `${source.source_id}:${source.page_number}`
    if (seen.has(key)) continue
    seen.add(key)
    targets.push({ source, text: segment.unit?.text ?? source.snippet })
    if (targets.length === MAX_PAGE_IMAGES) break
  }
  const images = await Promise.all(targets.map(async ({ source, text }) => {
    try {
      const preview = await fetchPagePreview({ source_type: "filesystem", source_id: source.source_id!, document_version: source.document_version!, page: source.page_number!, highlight: text })
      try { return { sourceId: source.source_id!, page: source.page_number!, dataUrl: await toDataUrl(preview.url), highlighted: preview.found } }
      finally { URL.revokeObjectURL(preview.url) }
    } catch { return null }
  }))
  return images.filter((image): image is PageImage => image !== null)
}

export async function downloadAnswerReport(turn: ResearchTurn): Promise<void> {
  const html = answerReportHtml(turn, await citedPageImages(turn))
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `${turn.question.replace(/[^\p{L}\p{N}\s_-]/gu, "").trim().slice(0, 60) || "research-answer"}.html`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
