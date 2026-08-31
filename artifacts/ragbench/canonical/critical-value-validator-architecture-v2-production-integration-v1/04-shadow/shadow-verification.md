# Shadow verification

The shadow flag is server-side and defaults to false. With baseline or V3
authoritative validation, Architecture V2 can run on the same immutable
claim/support inputs. The authoritative result is returned before/independent
of the diagnostic comparison; shadow failures set only a bounded error flag
and disagreement enum.

The bounded comparison is `SAME`, an authoritative outcome paired with
`ARCHV2_PASS`, `ARCHV2_REJECT`, or `ARCHV2_IND`, or `SHADOW_ERROR`.

When Architecture V2 is authoritative, a redundant V2 shadow is not run.
Both the existing V3 shadow and the Architecture V2 shadow are permitted
when their flags are explicitly enabled, because each is side-effect-free and
has separate bounded telemetry. No shadow path can alter visible output,
forced abstention, support IDs, citations, SSE, or HTTP status.

This task integrates capability only. Shadow remains disabled and actual
runtime/browser shadow readiness is a separate task.
