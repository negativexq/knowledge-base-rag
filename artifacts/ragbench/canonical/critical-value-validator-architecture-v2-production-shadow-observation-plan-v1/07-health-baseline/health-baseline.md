# Environment and attribution baseline

Track Qdrant, provider, API, OTel/Jaeger, and application health separately
from Architecture V2 shadow errors. Each incident receives exactly one bounded
primary attribution:

`ARCHITECTURE_V2`, `AUTHORITATIVE_VALIDATOR`, `RETRIEVAL`, `QDRANT`,
`PROVIDER`, `APPLICATION`, `TELEMETRY`, `ENVIRONMENT`, or `UNKNOWN`.

The local readiness reference included three transient Qdrant readiness poll
timeouts; they recovered and were not task-caused. A future observation must
capture equivalent health counters so this type of noise is not blamed on the
shadow.
