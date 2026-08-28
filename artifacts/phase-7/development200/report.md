# Development200 characterization

- Selected architecture: `pipeline_v2_2_evidence_backed`
- Config fingerprint: `680ca44af8b296526bd22b7d81a5388c59132da4fd42ff4f4cb968c2b1c2158d`
- Results: 200/200 accounted, provider failures: 0
- Hard safety gate: **HARD_SAFETY_PASS**
- Raw fully correct: 72
- Visible fully correct: 72
- Forced abstention: 56
- False abstention: 14
- Generation latency p50/p95/max: 29352.604 / 83224.628 / 104258.351 ms
- Blind attribution sample: 21 correctly attributed, 3 misattributed, 6 no visible factual claim

## Frozen characterization semantics

Ambiguous behavior is reported separately from task completeness. Injection security handling is reported separately from injection task completeness. The selected V2.2 pipeline retains known semantic attribution and multi-document limitations; Development200 does not reopen architecture selection.
