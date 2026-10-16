import type { IngestionQuality } from "@/api/types"

export interface QualitySummary {
  label: string
  status: "success" | "warning" | "default"
}

const OCR_REASON: Record<string, string> = {
  no_text_layer: "no text layer",
  garbled_text: "garbled text",
  vector_text: "vector text",
}

function ocrPageCount(quality: IngestionQuality): number {
  return Object.values(quality.ocr_pages).reduce((sum, count) => sum + count, 0)
}

/** One-line state of a document's last parse, for the documents table. */
export function qualitySummary(quality: IngestionQuality | null | undefined): QualitySummary {
  if (!quality) return { label: "Not reported", status: "default" }
  if (quality.needs_review) return { label: "Needs review", status: "warning" }
  const ocr = ocrPageCount(quality)
  return { label: ocr ? `OK · OCR ${ocr} pages` : "OK", status: "success" }
}

/** The full report as label/value rows, for the document detail panel. */
export function qualityRows(quality: IngestionQuality): [string, string][] {
  const ocr = ocrPageCount(quality)
  const entries = Object.entries(quality.ocr_pages)
  // One reason: "7 (garbled text)"; several: "3 (2 no text layer, 1 garbled text)".
  const reasons = entries
    .map(([reason, count]) => {
      const name = OCR_REASON[reason] ?? reason
      return entries.length === 1 ? name : `${count} ${name}`
    })
    .join(", ")
  return [
    ["Pages", String(quality.pages)],
    ["OCR pages", ocr ? `${ocr} (${reasons})` : "0"],
    ["Skipped pages", String(quality.skipped_pages)],
    ["Garbled blocks dropped", String(quality.garbled_blocks_dropped)],
    ["Empty pages", String(quality.empty_pages)],
    ["Headings", `${quality.headings} (${quality.heading_source})`],
    ["Tables", String(quality.tables)],
    ["Headers and footers removed", String(quality.furniture)],
  ]
}
