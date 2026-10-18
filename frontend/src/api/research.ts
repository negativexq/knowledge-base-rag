import { api } from "@/api/client"
import type { DocumentReadRequest, DocumentReadResult, FeedbackSubmission, FeedbackRecord } from "@/api/types"

export const researchApi = {
  feedback: (body: FeedbackSubmission) => api.post<FeedbackRecord>("/research/feedback", body),
  reports: (reviewer: boolean, offset = 0, status = "") => api.get<FeedbackRecord[]>(`/research/feedback${reviewer ? "" : "/mine"}?offset=${offset}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  review: (id: string, status: "triaged" | "resolved" | "dismissed", note: string) => api.post<FeedbackRecord>(`/research/feedback/${encodeURIComponent(id)}/review`, { status, note }),
  read: (body: DocumentReadRequest) => api.post<DocumentReadResult>("/research/documents/read", body),
}
