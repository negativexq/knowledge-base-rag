import { getToken } from "@/api/auth"
import { API_BASE_URL } from "@/api/client"
import { type ChatStreamHandlers, streamChat } from "@/lib/sse"

export const chatApi = {
  ask: (question: string, handlers: ChatStreamHandlers, signal?: AbortSignal) =>
    streamChat(`${API_BASE_URL}/chat`, getToken(), question, handlers, signal),
}
