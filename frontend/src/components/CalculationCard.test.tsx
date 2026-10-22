import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { SupportUnitRef } from "@/api/types"
import { CalculationCard } from "@/components/CalculationCard"

const unit = { support_id: "E1.S1", source_rank: 1, source_type: "pdf", source_id: "doc", section_label: "Lengths", text: "A 120 cm; B 2 m", page_number: 4 } as SupportUnitRef

describe("CalculationCard", () => {
  it("shows the formula, each cited input and the result", () => {
    const cite = vi.fn()
    render(<CalculationCard units={[unit]} onCite={cite} calculation={{
      id: "c", expression: "a+b", result: "3.20", unit: "m", support_ids: ["E1.S1"],
      inputs: [
        { name: "a", label: "A", value: "120", unit: "cm", support_id: "E1.S1", page: 4 },
        { name: "b", label: "B", value: "2", unit: "m", support_id: "E1.S1", page: 4 },
      ],
    }} />)
    expect(screen.getByText("120 cm")).toBeInTheDocument()
    expect(screen.getByText("3.20 m")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Open the source of b" }))
    expect(cite).toHaveBeenCalledWith(1, "E1.S1")
    expect(screen.getByText(/not by the model/)).toBeInTheDocument()
  })
})
