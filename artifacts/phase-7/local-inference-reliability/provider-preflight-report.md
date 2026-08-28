# Local Inference Reliability

Historical status: **PROVIDER_BLOCKED**

Recovery status: **PROVIDER_READY**

The original Python Probe A timed out before headers and the first body byte.
Direct HTTP remained responsive, and server logs showed an aborted/stale model
load after a client connection closed. A controlled model unload followed by
`SIGTERM ollama serve` and an Ollama relaunch produced a new server PID.

Post-recovery probes all completed:

- A plain: PASS, 419 ms
- B structured: PASS, 1.105 s
- C frozen V2.2 snapshot: PASS, 18.924 s
- D frozen V2.3 snapshot: PASS, 11.972 s
- five-call real V2.2 reliability: 5/5 PASS, max 7.712 s

M0 stability (50 calls) and the V2.2 baseline (55 calls) completed without
provider failures and the V2.2 baseline was frozen. The later V2.3 paired run
encountered two bounded read timeouts on a larger dynamic support-unit request;
its quality decision is therefore **NOT_EVALUATED** and its execution status is
**PROVIDER_UNSTABLE**. No smoke36 or development200 run was started.
