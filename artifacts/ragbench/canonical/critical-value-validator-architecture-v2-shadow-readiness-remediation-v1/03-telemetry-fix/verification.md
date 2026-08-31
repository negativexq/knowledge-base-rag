# Telemetry promotion verification

The production request aggregate now receives shadow fields from every
successful `audit_critical_value()` result. The aggregate counts are summed
from the immutable V2 result metadata, not re-derived from text or forensic
content. The span records `executed=true` for a successful zero-occurrence
run, while disabled/error cases remain `executed=false`.

Actual Jaeger smoke evidence is in `08-runtime-smoke/jaeger-smoke.json`.
