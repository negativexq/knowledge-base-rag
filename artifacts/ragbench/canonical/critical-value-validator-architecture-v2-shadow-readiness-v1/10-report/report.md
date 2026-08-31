# Shadow readiness report

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_SHADOW_READINESS_FAILED`

The controlled local API path proved that baseline remained authoritative and
V2 shadow executed on 5/5 validator-capable requests. The decision is not a
semantic failure. Readiness cannot pass because the required real browser UI
execution was unavailable and the actual OTel aggregate span did not expose
the required V2 architecture ID and occurrence/role counts.

## Runtime

- Environment: LOCAL
- Provider: Ollama fallback, `qwen3.5:4b`
- API: `127.0.0.1:8001`
- Frontend: `127.0.0.1:5174`
- Authoritative validator: baseline
- V2 shadow: enabled only in the controlled process
- V3 shadow: disabled
- Primary requests: 6 controlled HTTP fallback requests
- Validator-capable requests: 5
- V2 shadow executions: 5
- Shadow coverage: 100% of validator-capable HTTP requests
- Normal shadow errors: 0

The Chrome CDP endpoint was present on port 9222, but the browser-control
connector reported Chrome unavailable and could not attach. The in-app browser
was also unavailable. No browser UI result is claimed.

## Safety

The API path returned normally with baseline authoritative. Deterministic
failure-injection tests proved shadow exception isolation and authoritative
fail-closed behavior. OTel payload inspection found zero raw-content or secret
leaks. Forensic capture contracts passed with raw capture disabled by default.

## Required follow-up

Do not activate production shadow. Resolve the telemetry promotion gap and run
the real Chrome UI path in a browser-capable environment. This task did not
change Architecture V2 semantics, defaults, selectors, or production state.
