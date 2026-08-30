# Critical-Value Validator Forensic V1

## Scope and integrity

This is an offline forensic of the frozen corrected TechQA execution. No
retrieval, embedding, BGE, Luna, Terra, Ollama, provider call, semantic
rescore, threshold tuning, or validator code change was performed.

The source artifacts were sidecar-verified where sidecars exist. The frozen
architecture verdict remains `BGE_REMOVAL_NOT_SUPPORTED`; semantic labels and
canonical artifacts were not modified. Source hash recheck at report time:
`PASS`.

## Population

There are 14 ON and 21 OFF critical-reject query-arm rows, and 78 rejecting claim-local critical-value events (30 ON, 48 OFF).

The event unit is query × arm × answer part × critical value. Supported
critical tokens in a mixed answer part are not counted as rejecting events.

## Adjudication

| Event class | Count |
| --- | ---: |
| TRUE_CONFLICT | 0 |
| FALSE_POSITIVE | 26 |
| INDETERMINATE | 52 |

Determinate precision is 0/26 = 0.0%; determinate false-positive rate is 26/26 = 100.0%. Indeterminate events are excluded from both rates.

The primary forensic conclusion is **VALIDATOR_CALIBRATION_INCONCLUSIVE**. This classification is
conservative: an unresolved validator trace is not treated as a false
positive merely because the final answer was unavailable.

### Representative false-positive patterns

- **CLAIM_SUPPORT_ALIGNMENT** (3 events): CV-006 (techqa_DEV_Q277#row-0042, OFF): claim literal '8.0'; support/validator values '5.0;8.5'. Claim: For WebSphere Portal 8.5, transient user support for the SAML TAI was introduced starting with Cumulative Fix 8. The supplied documentation does not state that this support was available for Portal 8.0. Support: Transient user support [http://www-01.ibm.com/support/knowledgecenter/SSHRKX_8.5.0/mp/overview/new_cf08.dita?lang=en] has been introduced for SAML TAI [http://www-01.ibm.com/support/knowledgecenter/SSHRKX_8.5.0/mp/wcm/wcm_secure_int_tai_auth.dita?lang=en] starting with Cumulative Fix (CF) #8 for 8.5. Refer to the WebSphere Portal Security blog [https://www.i
- **EXTRACTION_ERROR** (3 events): CV-025 (techqa_DEV_Q035#row-0121, OFF): claim literal '2017'; support/validator values '8'. Claim: The information is in the IBM API Connect Security Bulletin. It identifies CVE-2017-14919 as a Node.js denial-of-service vulnerability in the zlib module: a remote attacker can supply an invalid windowBits value of 8, triggering an uncaught exception and crash Support: SUMMARY IBM API Connect has addressed the following vulnerability. || Node.js is vulnerable to a denial of service, caused by an uncaught exception flaw in the zlib module. By making 8 an invalid value for the windowBits parameter, a remote attacker could exploit this vulnerability to cause the application to crash. || VULNERABILITY DETAILS CVEID:CVE-2017-14
- **NUMERIC_EQUIVALENCE** (8 events): CV-047 (techqa_DEV_Q012#row-0133, OFF): claim literal '131.072'; support/validator values '131072'. Claim: The error occurs because the system’s ARG_MAX setting limits the command-line argument list, and the UDX compilation used more than 131,072 arguments, including many .c files. Support: CAUSE ARG_MAX configuration parameter limits the number of argument list in command line. In this case the client used more than 131072 argument with many program *.c files.
- **SUPPORT_SEGMENTATION** (3 events): CV-023 (techqa_DEV_Q218#row-0137, OFF): claim literal '8.0.0.2'; support/validator values '1.0.0.2;2.1.2.0;2.2.0.0'. Claim: The deployed VM shows MQ 8.0.0.2 because the PureApplication System interface change in versions 2.1.2.0 and 2.2.0.0 or later causes installation or upgrade of the latest MQ maintenance level in older MQ pattern types to appear successful while the subsequent  Support: This affects users with IBM MQ Pure Application System pattern-types 1.0.0.2 and earlier. CAUSE Because of an interface change in IBM Pure Application System 2.1.2.0, and in 2.2.0.0 and greater, installation and upgrade of IBM MQ at the latest maintenance level contained in the pattern-type fails. The installation appears to succeed, but IBM MQ 8.0.0.2 is in
- **VERSION_FORMAT** (9 events): CV-004 (techqa_DEV_Q126#row-0066, ON): claim literal '7.0.1'; support/validator values '7.0.1.11;7.0.1.10'. Claim: The failure is caused by a WebSphere MQ Classes for JMS V7.0.1 client defect: during JMS Session connection, the client erroneously set SSLPEERNAME from the certificate’s distinguished name. MQ then returned MQRC_SSL_PEER_NAME_ERROR (2399), reported as AMQ9640 Support: ERROR DESCRIPTION * A WebSphere MQ classes for Java Message Service (JMS) or WebSphere MQ classes for Java client application using WebSphere MQ Version 7.0.1.11 jar files, tries to make a connection to a queue manager secured with SSL/TLS. This fails with a JMSException, with reason code MQRC_SSL_PEER_NAME_ERROR. The exception is similar to: . com.ibm.mq.jm

## Arm and availability accounting

| Measure | ON | OFF |
| --- | ---: | ---: |
| Critical-reject queries | 14 | 21 |
| Critical-reject events | 30 | 48 |
| Critical reject + forced abstain | 3 | 6 |
| Critical reject + no forced abstain | 11 | 15 |
| No critical reject + forced abstain | 2 | 4 |
| Critical reject + unavailable | 3 | 6 |
| Critical reject + available | 11 | 15 |
| No critical reject + unavailable | 11 | 12 |

P(forced abstain | critical reject) is 0.214 ON and 0.286 OFF.

Availability transitions are: ON available → OFF unavailable 7; ON unavailable → OFF available 3; both available 29; both unavailable 11. The exact OFF unavailable delta is 4: OFF has 18 unavailable and ON has 14. The transition table identifies the contributing query IDs; no counterfactual quality is assigned.

OFF-only critical-reject queries: 10. ON-only: 3. Both arms: 11. These are query-level sets, not an assertion that the event-count difference is caused by one event per query.

## Interpretation

Proven: the frozen validator emitted the observed claim-local reject and
indeterminate traces, and the adjudication above follows the attached
model-visible support units and persisted validator trace. OFF has more
critical-reject query arms and more rejecting events in this run.

Only correlated: OFF's larger critical-reject population coincides with more
unavailable outputs. This does not establish that the validator caused all of
the semantic availability difference, or that accepting a rejected claim
would make it correct.

Unknown: there is no new counterfactual semantic score. Frozen semantic labels
remain authoritative and were not rescored.

## Calibration follow-up

No production validator change is authorized by this forensic. Any follow-up
should be a preregistered DEBUG/dev calibration experiment, developed outside
the consumed HOLDOUT and validated on a new evaluation population.

- P0: review numeric normalization patterns represented by any confirmed
  representation-only events; do not tune from this HOLDOUT alone.
- P1: review unit/date/version canonicalization only if a corresponding
  false-positive subtype is present in the adjudication table.
- P2: review support segmentation and claim-support alignment for unresolved
  traces; preserve claim-locality and fail-closed behavior.

HOLDOUT forensic informs mechanism understanding only; calibration must be
developed on DEBUG/dev and validated on a new evaluation population.

## Artifact index

- `02-event-table/critical-validator-events.csv`: rejecting event table.
- `03-adjudication/event-adjudications.csv`: one conservative class per event.
- `04-query-summary/query-arm-summary.csv`: one row per query × arm.
- `04-query-summary/availability-transitions.csv`: paired availability map.
- `05-aggregate/*.json`: arm, calibration, and semantic consequence summaries.

No canonical source artifact was overwritten.
