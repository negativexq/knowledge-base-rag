# Pilot fixture caveat

This run used ambiguous initial evidence: "The service uses TLS." The search
cases asked about the backup service, with SSH available only through search.
The model answered TLS without searching in all four follow-up runs. This is a
quality signal but the primary/backup referent was underspecified. The v2 run
uses "The primary service uses TLS." to disambiguate it without changing agent
prompts or validators.

The pilot's original summary is preserved. Its 24 security passes mean no
observed marker/ACL violation; two poisoned-tool scenarios were never reached
and should be treated as inconclusive coverage, not successful attack resistance.
The v2 runner explicitly reports unexercised scenarios as inconclusive.
