import { useState } from "react"
import type { Clarification } from "@/api/types"
import { Button } from "@/components/ui/button"

export function ClarificationPrompt({ clarification, disabled, onReply }: {
  clarification: Clarification; disabled: boolean; onReply: (answer: string) => void
}) {
  const [answer, setAnswer] = useState("")
  return <form aria-label="Clarify your question" onSubmit={(event) => { event.preventDefault(); if (answer.trim()) onReply(answer.trim()) }} className="space-y-3 rounded-lg border border-[var(--color-border)] p-4">
    <p className="text-sm font-medium">{clarification.question}</p>
    {clarification.options.length > 0 && <div className="flex flex-wrap gap-2">{clarification.options.map((option) => <Button type="button" variant="secondary" size="sm" key={option} disabled={disabled} onClick={() => onReply(option)}>{option}</Button>)}</div>}
    <label className="block text-xs">Your clarification<input value={answer} maxLength={2000} disabled={disabled} onChange={(event) => setAnswer(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2 text-sm" /></label>
    <Button size="sm" disabled={disabled || !answer.trim()}>Continue research</Button>
  </form>
}
