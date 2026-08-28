# M0 Stability Audit

{
  "same_seed_query_count": 5,
  "cross_seed_query_count": 5,
  "same_seed_runs": 25,
  "cross_seed_runs": 25,
  "retrieval_stable": true,
  "rerank_stable": true,
  "evidence_context_stable": true,
  "generation_same_seed_stable": true,
  "cross_seed_content_stability": {
    "multi_document": 1,
    "acl": 1,
    "standard": 1,
    "cross_lingual": 1,
    "authority_version": 1
  },
  "cross_seed_support_selection_stability": {
    "multi_document": 1,
    "acl": 1,
    "standard": 1,
    "cross_lingual": 1,
    "authority_version": 1
  },
  "raw_output_hashes": {
    "same_seed:multi_document": [
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5"
    ],
    "same_seed:acl": [
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb"
    ],
    "same_seed:standard": [
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6"
    ],
    "same_seed:cross_lingual": [
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea"
    ],
    "same_seed:authority_version": [
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b"
    ],
    "cross_seed:multi_document": [
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5",
      "53185efdaef697ede5ceaf9f757cde67a6208a3f51934efe1f93ff368747c9e5"
    ],
    "cross_seed:acl": [
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb",
      "73245349d1d43a0325466bcf08bfc56c5be886c23f9a4b515c79be3ad797c3cb"
    ],
    "cross_seed:standard": [
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6",
      "ca2bcd8786b047256e3faa2ca66285d8e9dd9702a9376b1b39b8a578a185eff6"
    ],
    "cross_seed:cross_lingual": [
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea",
      "3049bbcc53f0c8ef2b6aa00bf4d16a762f722bea0f62b4be690f2d4de05332ea"
    ],
    "cross_seed:authority_version": [
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b",
      "e66f04d25a3bfdad697840afe34b2ddb5beaa51134507995dacbb2594c546e0b"
    ]
  }
}
