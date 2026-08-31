# V6 candidate delta

V6 is a DEBUG-only challenger over the frozen V5 polarity guard. It adds a
typed, non-overlapping occurrence ledger with explicit sign ownership and
full-span ownership for CVE/SQLCODE literals. It removes only exact rejected
premise spans using length-preserving masking. V5 polarity semantics and all
production behavior remain unchanged.

The frozen V4 and V5 helper regions are verified unchanged. V6 is absent from
the production `baseline|v3` selector.
