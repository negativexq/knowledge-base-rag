# Staged rollout plan

This review authorizes no runtime change. If a separate implementation task is
approved, the progression is:

1. integrate behind a server-side selector;
2. keep `baseline` as default;
3. keep Architecture V2 shadow disabled by default;
4. run local/staging shadow with controlled UI E2E;
5. inspect bounded disagreements and shadow errors;
6. review rollback and telemetry;
7. consider production shadow only after the shadow gates pass;
8. consider canary only in a later, separately authorized task.

Future shadow gates should include zero security regressions, zero raw OTel
leakage, isolated shadow errors, understood disagreements, acceptable local
latency, unchanged authoritative responses, and verified rollback.

No production shadow, canary, or promotion is authorized here.
