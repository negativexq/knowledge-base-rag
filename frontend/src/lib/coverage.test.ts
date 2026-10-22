import { describe, expect, it } from "vitest"
import type { DocumentRecord, IngestionQuality } from "@/api/types"
import { documentCoverage } from "@/lib/coverage"

const quality = (patch: Partial<IngestionQuality> = {}) => ({ pages: 10, ocr_pages: {}, needs_review: false, ...patch }) as IngestionQuality
const doc = (id: string, status = "active", q: IngestionQuality | null = quality()) => ({ source_id: id, status, ingestion_quality: q }) as DocumentRecord

describe("documentCoverage", () => {
  it("counts searchable, scanned, flagged and unavailable documents", () => {
    const coverage = documentCoverage([
      doc("a"), doc("b", "active", quality({ ocr_pages: { tesseract: 3 } })),
      doc("c", "active", quality({ needs_review: true })), doc("d", "error"),
    ])
    expect(coverage).toMatchObject({ searchable: 3, scanned: 1, needsReview: 1, unavailable: 1 })
    expect(coverage.notes).toHaveLength(3)
    expect(coverage.notes[0]).toMatch(/^1 document has scanned pages/)
  })

  it("has no notes when everything is clean", () => {
    expect(documentCoverage([doc("a"), doc("b", "active", null)]).notes).toEqual([])
  })
})
