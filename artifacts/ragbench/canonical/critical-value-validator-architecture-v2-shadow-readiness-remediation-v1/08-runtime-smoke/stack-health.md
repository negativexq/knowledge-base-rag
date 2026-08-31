# Controlled local stack health

- Qdrant `127.0.0.1:6333`: HTTP 200.
- Jaeger `127.0.0.1:16686`: HTTP 200.
- Remediation API `127.0.0.1:8001`: `/health` HTTP 200 and `/chat` HTTP 200.
- Remediation frontend `127.0.0.1:5174`: HTTP 200.
- Chrome CDP `127.0.0.1:9222`: `/json/version` and `/json/list` available.

One readiness-poll request returned a transient 500 while Qdrant alias
inspection timed out; subsequent readiness polls and the chat requests were
successful. The trace and browser flow were not affected. This was an
environmental Qdrant health-poll condition, not a telemetry or browser-path
regression.
