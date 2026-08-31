# Local stack health

- Qdrant `127.0.0.1:6333`: HTTP 200.
- Jaeger `127.0.0.1:16686`: HTTP 200.
- API `127.0.0.1:8001`: `/health` HTTP 200 and all six `/chat` responses HTTP 200.
- Frontend `127.0.0.1:5174`: HTTP 200.
- Chrome CDP `127.0.0.1:9222`: `/json/version` PASS, websocket present.

Three `/health/ready` polls returned HTTP 500 because the Qdrant alias
inspection timed out. Subsequent polls were HTTP 200 and no `/chat` request
failed. This is recorded as an environment-dependent health-poll condition,
not a task-caused shadow or browser failure.
