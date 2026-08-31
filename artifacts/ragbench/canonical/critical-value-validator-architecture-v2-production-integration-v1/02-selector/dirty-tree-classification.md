# Dirty-tree classification

The worktree contains pre-existing uncommitted research and forensic changes.
This integration task added or changed only these scoped paths:

- production integration: `app/evaluation/critical_validator_runtime.py`,
  `app/shared/config.py`, `app/api/chat.py`, `app/wiring.py`,
  `app/evidence/support_relevance.py`, `app/llm/structured_output.py`, and
  `app/evaluation/forensic_capture.py`;
- reusable integration tests:
  `tests/test_critical_validator_architecture_v2_integration.py`;
- configuration: `.env.example`;
- documentation: `docs/critical-validator-architecture-v2-rollout.md`;
- canonical evidence: this artifact root.

Other dirty application paths (`app/evaluation/critical_values.py`, provider,
retrieval, and existing test changes), prior experimental V2 modules, and
earlier canonical roots are preserved as pre-existing work and were not
cleaned or committed. A future integration commit should include only the
scoped selector/adapter/wiring, privacy/forensic support, tests, config/docs,
and this new evidence root after review.
