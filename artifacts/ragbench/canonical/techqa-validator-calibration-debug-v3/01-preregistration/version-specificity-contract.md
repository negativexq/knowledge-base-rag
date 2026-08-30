# Version specificity contract

An explicitly family-scoped claim (`family`, `series`, `major version`, `.x`,
or `or later`) may match a compatible support version. Major-family claims
match the same major; minor-family claims match the same major and minor.

Explicit exact claims and fully specified three-component versions require
component equality. Optional leading `v` is syntax only. A shorter version
string without family wording is not automatically a family claim; unresolved
major/minor specificity is `INDETERMINATE`.

The guard is local and deterministic. It does not use release lifecycle
knowledge, locale inference, global evidence search, or semantic entailment.
