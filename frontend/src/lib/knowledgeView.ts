export type KnowledgeColumn = "version" | "chunk_count" | "quality" | "status" | "last_synced_at"
export type KnowledgeSort = KnowledgeColumn | "source_id"
export interface KnowledgePreferences { columns: KnowledgeColumn[]; compact: boolean }
export interface KnowledgeView extends KnowledgePreferences {
  source: string | null
  search: string
  status: string
  quality: string
  sort: { key: KnowledgeSort; descending: boolean }
  page: number
  pageSize: number
}
export const knowledgeColumns: { key: KnowledgeColumn; label: string }[] = [
  { key: "version", label: "Version" }, { key: "chunk_count", label: "Chunks" },
  { key: "quality", label: "Quality" }, { key: "status", label: "Status" }, { key: "last_synced_at", label: "Updated" },
]
const defaultPreferences: KnowledgePreferences = { columns: knowledgeColumns.map((column) => column.key), compact: false }
export function readKnowledgeView(search: string, preferences = defaultPreferences): KnowledgeView {
  const params = new URLSearchParams(search)
  const sortKey = params.get("sort")
  const page = Number(params.get("page") ?? 1)
  const rows = Number(params.get("rows") ?? 25)
  return {
    source: params.get("source")?.slice(0, 128) || null,
    search: params.get("q")?.slice(0, 500) ?? "",
    status: params.get("status")?.slice(0, 100) ?? "",
    quality: ["review", "ok", "missing"].includes(params.get("quality") ?? "") ? params.get("quality")! : "",
    sort: { key: sortKey === "source_id" || knowledgeColumns.some((column) => column.key === sortKey) ? sortKey as KnowledgeSort : "source_id", descending: params.get("order") === "desc" },
    columns: params.has("columns") ? knowledgeColumns.filter((column) => params.get("columns")!.split(",").includes(column.key)).map((column) => column.key) : preferences.columns,
    compact: params.has("density") ? params.get("density") === "compact" : preferences.compact,
    page: Number.isInteger(page) && page > 0 && page <= 100000 ? page - 1 : 0,
    pageSize: [10, 25, 50, 100].includes(rows) ? rows : 25,
  }
}
export function knowledgeViewQuery(view: KnowledgeView): Record<string, string | null> {
  return { source: view.source, q: view.search || null, status: view.status || null, quality: view.quality || null,
    sort: view.sort.key, order: view.sort.descending ? "desc" : "asc", columns: view.columns.join(","),
    density: view.compact ? "compact" : "comfortable", rows: String(view.pageSize), page: String(view.page + 1) }
}
