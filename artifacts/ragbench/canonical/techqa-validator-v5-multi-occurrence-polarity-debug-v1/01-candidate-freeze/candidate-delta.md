# V5 candidate delta

V5 is a DEBUG-only challenger over the frozen V4 polarity guard. It adds
occurrence-local same-surface sibling detection and length-preserving masking
of only the exact rejected-premise span. It does not change V3 or V4 source,
production selector behavior, critical-value type normalization, or any RAG
pipeline component.

The V4 helper region remains byte-identical to the frozen hash. V5 is not
available through the production `baseline|v3` selector.
