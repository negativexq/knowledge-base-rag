import { describe, expect, it } from "vitest"

import type { IngestionQuality } from "@/api/types"
import { qualityRows, qualitySummary } from "@/lib/quality"

const clean: IngestionQuality = {
  pages: 12,
  ocr_pages: {},
  skipped_pages: 0,
  garbled_blocks_dropped: 0,
  empty_pages: 0,
  headings: 9,
  tables: 2,
  furniture: 12,
  heading_source: "layout",
  needs_review: false,
}

describe("qualitySummary", () => {
  it("reports a missing report plainly", () => {
    expect(qualitySummary(null)).toEqual({ label: "Not reported", status: "default" })
    expect(qualitySummary(undefined)).toEqual({ label: "Not reported", status: "default" })
  })

  it("marks a clean parse as OK and mentions OCR pages", () => {
    expect(qualitySummary(clean)).toEqual({ label: "OK", status: "success" })
    expect(qualitySummary({ ...clean, ocr_pages: { no_text_layer: 2, garbled_text: 1 } })).toEqual(
      { label: "OK · OCR 3 pages", status: "success" },
    )
  })

  it("flags a parse that lost text", () => {
    expect(qualitySummary({ ...clean, skipped_pages: 1, needs_review: true })).toEqual({
      label: "Needs review",
      status: "warning",
    })
  })
})

describe("qualityRows", () => {
  it("lists the report as label/value pairs", () => {
    const rows = qualityRows({ ...clean, ocr_pages: { garbled_text: 7 }, garbled_blocks_dropped: 0 })
    expect(rows).toContainEqual(["Pages", "12"])
    expect(rows).toContainEqual(["OCR pages", "7 (garbled text)"])
    expect(rows).toContainEqual(["Headings", "9 (layout)"])
    expect(rows).toContainEqual(["Skipped pages", "0"])
  })
})
