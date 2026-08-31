# Controlled stack health

Environment: local controlled runtime. The existing application on port 8000
was not used; the shadow-readiness API ran on 127.0.0.1:8001 and the Vite UI
on 127.0.0.1:5174.

| Component | Check | Result |
|---|---|---|
| API | `GET /health` on 8001 | HTTP 200, `status=ok` |
| Frontend | HTTP GET on 5174 | HTTP 200 |
| Qdrant | `GET /healthz` on 6333 | HTTP 200, healthz check passed |
| Jaeger | `/api/services` on 16686 | HTTP 200, `knowledge-base-rag` present |
| OTLP | 4317/4318 listening | PASS |
| Ollama | `/api/tags` on 11434 | HTTP 200 |
| Chrome CDP | 9222 `/json/version` | endpoint present |

The browser-control connector could not attach to the already-running Chrome
instance, and the in-app browser connector was also unavailable. Therefore the
frontend was started and health-checked, but a browser UI submission was not
performed. The HTTP requests below are runtime fallback evidence, not browser
E2E evidence.
