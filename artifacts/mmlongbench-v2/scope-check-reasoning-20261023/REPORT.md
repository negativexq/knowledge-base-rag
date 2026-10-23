# Scope and check reasoning effort: low vs medium replay (2026-10-23)

Ten MMLongBench rows (210, 370, 383, 471, 472, 509, 659, 727, 1013, 1073) were
run on `gpt-6-luna` with raw-text forensic capture, which now records each
model call's exact input. The 11 recorded `scope_validator` (9) and
`quantity_checker` (2) calls were then replayed with
`scripts/experiments/replay_model_calls.py`, unchanged except for the
reasoning effort: once at `low` and once again at the recorded `medium`.
The `medium` replay gives the run-to-run noise to compare `low` against.

| | low | medium (replay) |
|---|---|---|
| pass/fail agrees with the recorded call | 9/11 | 10/11 |
| identical verdict fields | 9/11 | 10/11 |
| mean latency | 3.9 s | 7.5 s |
| mean output tokens | 358 | 849 |

Low and the medium replay agree on pass/fail in 10 of 11 calls.

- **Row 210, scope.** The recorded call passed (the answer was correct). Both
  replays rejected it as `insufficient`, each with one objection. The
  disagreement is not caused by the effort; it is noise, at medium too.
- **Row 370, second scope call.** The recorded call and the medium replay
  passed; low objected with a `mismatch`. The answer was correct, so this is a
  false rejection at low only. In a live run it would cost a repair round or
  an abstention.
- Both quantity checker calls agreed at both efforts, but two calls are too
  few to say anything about the checker.

Low halves the latency and cuts output tokens by 58% on these calls. It also
showed one false rejection that medium did not, out of 11 calls. That is
not enough evidence to change the default either way. `ADAPTIVE_SCOPE_REASONING`
and `ADAPTIVE_CHECK_REASONING` are unset by default and inherit
`ADAPTIVE_FINAL_REASONING` (medium). A decision needs a larger replay set,
preferably with rows whose recorded scope verdict was a rejection.

Tokens: collection 275,283 input / 19,652 output; replay 175,614 input /
13,277 output. Per-call results are in `report.json`; run directories and
`replays.jsonl` stay untracked.
