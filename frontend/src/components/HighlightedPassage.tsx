import { Fragment } from "react"
import { passageMatches } from "@/lib/passageSearch"

export function HighlightedPassage({ text, query, prefix, activeId }: { text: string; query: string; prefix: string; activeId?: string }) {
  const matches = passageMatches(text, query, prefix)
  if (!matches.length) return <>{text}</>
  const last = matches[matches.length - 1]
  return <>{matches.map((match, index) => {
    const previous = matches[index - 1]
    return <Fragment key={match.id}>{text.slice(previous ? previous.start + previous.length : 0, match.start)}<mark data-match-id={match.id} data-active={match.id === activeId}
      className={match.id === activeId ? "rounded-sm bg-[var(--color-accent)] text-[var(--color-accent-foreground)]" : "rounded-sm bg-[var(--color-warning-muted)] text-[var(--color-foreground)]"}>{text.slice(match.start, match.start + match.length)}</mark></Fragment>
  })}{text.slice(last.start + last.length)}</>
}
