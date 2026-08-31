# C57 regression anchor

answer: 'The signed result is -204, not 204.'

Expected O1: raw=-204, role=VALIDATE.
Expected O2: raw=204, role=SKIP_REJECTED_PREMISE.
Expected nested 204 inside -204: NON_INDEPENDENT_NESTED_MATCH.

V5 occurrences: [('204', 22, 25, 'POSITIVE_ASSERTION'), ('204', 31, 34, 'REJECTED_PREMISE')]
V6 occurrences: [('-204', 21, 25, 'POSITIVE_ASSERTION'), ('204', 31, 34, 'REJECTED_PREMISE')]

V6 owns the sign in the -204 span and preserves the later standalone 204 span.
