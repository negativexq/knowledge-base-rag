# Source and repository identity

- Branch: `main`
- HEAD: `b3714f065ce9be65beaed000dde544648b68c860`
- Upstream: `origin/main` at the same commit.
- Working tree: clean.
- The previously reported evidence checkpoint `433e1e5` is followed by the
  later lint-only checkpoint `b3714f0`; frozen Architecture V2 semantic files
  remain unchanged.
- Architecture ID:
  `CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1`.
- Semantic/source digest:
  `09d94bb7c9d1769bd79e18c0beaa75c653477d3127605fdbcaddc5e9cf7ed33b`.
- Raw freeze-manifest SHA256:
  `c797556bff29669cdafdb165646b601e94ce4a1573969dd69b9e452f2d080d23`.

Frozen semantic source hashes at plan time:

```text
app/evaluation/critical_occurrences.py d00423ab6f7f9777ff7bd20161f1372a263a6d78127ee670418e178eadbb005f
app/evaluation/critical_roles.py e74a7c63c0f132fe390aacd4bf7a1bb51aceeedd0d81673cd6230b252378b83f
app/evaluation/critical_occurrence_validation.py 17adc1b0c76ea83c5a596e9bc19b0f4ec4fe1101f13145d4cf687cf9c74f2ad8
app/evaluation/critical_validator_architecture_v2.py b83657326f67533c0e3b4b854e7682cb3559452a7dc97caf65fe332ecc9ebc35
scripts/run_validator_calibration_debug_v3.py 44dd8bdd2c0b5468248870563d305773d1931ef7709ecf2ed145188b708a54b1
```

No production shadow was enabled and no production traffic was used for this
plan.
