# Sample record audit

The sample was produced with a synthetic, non-sensitive support unit and a
deterministic fake provider. It used both explicit local switches:

- `RAG_FORENSIC_CAPTURE_ENABLED=true`
- `RAG_FORENSIC_CAPTURE_RAW_TEXT=true`

No external provider, retrieval, embedding, or BGE call was made.

| Forensic question | Result |
|---|---|
| Correct evidence in Top20? | ANSWERABLE |
| Evidence removed by BGE? | ANSWERABLE |
| EvidenceBuildResult included it? | ANSWERABLE |
| Exact evidence seen by generation? | ANSWERABLE |
| Raw semantic model answer? | ANSWERABLE |
| Model support IDs? | ANSWERABLE |
| Accepted support IDs? | ANSWERABLE |
| Critical literal/input and result? | ANSWERABLE |
| Baseline decision? | ANSWERABLE |
| V3 shadow decision? | ANSWERABLE |
| Forced-abstain transition? | ANSWERABLE |
| Citation resolution? | ANSWERABLE |
| User-visible outcome? | ANSWERABLE |

## Result

**13/13 ANSWERABLE.** The record is local-only and contains synthetic raw text;
the same fields are omitted from normal OTel and metadata-only capture.

Sample record:
`captures-final/213150f685c84a89acde514805be8af5.json`

SHA256:
`e6ae0495b5e119623dd4cffff496fe60ad07e04cb30d4c6442fa17de73527b2f`
