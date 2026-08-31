# Focused forensic tests

- default capture disabled: PASS
- raw mode requires explicit capture enablement: PASS
- disabled mode writes nothing: PASS
- metadata mode omits raw content: PASS
- raw local mode redacts secret-like fields: PASS
- OTel redaction omits raw content: PASS
- capture write failure is non-fatal: PASS
- chunk metadata is bounded: PASS
- generation/validation/citation/visible capture chain: PASS

No provider calls were made by these tests.
