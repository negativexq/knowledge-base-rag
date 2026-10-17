export function passageMatches(text: string, query: string, prefix: string) {
  if (!query.trim()) return []
  const escaped = query.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return [...text.matchAll(new RegExp(escaped, "giu"))].map((match, index) => ({ id: `${prefix}:${index}`, start: match.index!, length: match[0].length }))
}

