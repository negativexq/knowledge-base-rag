# Privacy contract

Production shadow artifacts and normal OTel may contain only aggregate counts,
bounded enums, booleans, durations, configuration state, and the bounded
Architecture ID/version.

Forbidden: raw query, answer, evidence, support/document text, critical or
normalized literals, occurrence IDs/spans, claim text, prompts, headers,
cookies, API keys, user identity, unnecessary tenant/document identifiers, and
free-form exception text.

Any raw-content or secret leak immediately stops observation and disables the
shadow flag. If investigation needs raw content, reproduce locally with safe
synthetic data instead.
