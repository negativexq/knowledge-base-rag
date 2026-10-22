import type { DocumentRecord } from "@/api/types"

export interface Coverage {
  searchable: number
  unavailable: number
  scanned: number
  needsReview: number
  notes: string[]
}

// What a question will search, from the registry the Knowledge page shows.
export function documentCoverage(documents: DocumentRecord[]): Coverage {
  const searchable = documents.filter((doc) => doc.status === "active")
  const scanned = searchable.filter((doc) => Object.values(doc.ingestion_quality?.ocr_pages ?? {}).some((count) => count > 0))
  const needsReview = searchable.filter((doc) => doc.ingestion_quality?.needs_review)
  const unavailable = documents.length - searchable.length
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  const notes = [
    scanned.length ? `${plural(scanned.length, "document has", "documents have")} scanned pages read with OCR; tables and charts there take longer and may be less exact.` : null,
    needsReview.length ? `${plural(needsReview.length, "document was", "documents were")} flagged for review at ingestion.` : null,
    unavailable ? `${plural(unavailable, "document is", "documents are")} not searchable right now (not active in the index).` : null,
  ].filter((note): note is string => note !== null)
  return { searchable: searchable.length, unavailable, scanned: scanned.length, needsReview: needsReview.length, notes }
}
