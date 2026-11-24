# Thesis readiness report

## 1. Executive summary

The isolated implementation now has a working small Flower-to-SPDZ2k path, a tested weighted aggregation helper, protected party control, and direct MPC measurements through 100,000 parameters. Full CNN secure aggregation remains incomplete: 250k and the earlier 2,122,187-parameter direct attempts did not return aggregates under a 300-second cap, and no full-model Flower round was run. The evidence is suitable for careful technical writing, but not for claims of a validated full-scale hybrid defense.

## 2. What is implemented

The branch implements Flower client selection/training and aggregation, an MP-SPDZ v0.4.3 SPDZ2k weighted-sum circuit, fixed-point encoding and chunked input transfer, sample-count binding, designated aggregate output, HMAC-authenticated/replay-protected party control, bytecode identity checks, abort/cleanup, MTD client scheduling, and a plaintext robust-update detector that is disallowed with sum-only SMPC. Secure mode has no plaintext or additive-sharing fallback.

## 3. What has been experimentally verified

- Full automated suite, run 2026-11-18 against the isolated source: 77 passed, 2 Typer/Click deprecation warnings in 5.50 s after the engineering regression additions.
- Python compileall and `git diff --check`: pass.
- Wheel: successful via installed setuptools backend; circuit included, removed additive-sharing modules absent.
- Same-host tiny Flower/SPDZ2k one-round run: 3 clients/parties, 8 parameters, 16.32 s total, 0.807365 s aggregation, zero fit failures.
- Direct production circuit: exact deterministic Python-reference output at 8, 1k, corrected 10k, 50k and 100k; max error 0 and count validation passed.
- Party control authentication/replay, persistence, configuration rejection, secure output length/count, and several failure-cleanup code paths have automated unit coverage.

## 4. Main experimental findings

The largest completed direct test was 100k parameters (246.236 s total, approximately 197 s offline/preprocessing, 17 s online, 42,999.4 MB global protocol traffic, ~388?391 MiB peak party RSS). At 250k the 300-second watchdog stopped the run after client connections; no aggregate was returned. The old full-size direct attempt also timed out without an aggregate. Offline/preprocessing and its communication dominate the measured large runs.

## 5. Security properties and assumptions

MP-SPDZ v0.4.3 classifies SPDZ2k as malicious security with dishonest majority. The deployment assumes at least one aggregation party remains honest; parties may force abort. The service launches the parties with `-e` and local demo provisions SSL material, but tests are loopback-only. Coordinator receives the aggregate and count, not individual plaintext model vectors; it still sees cohort metadata and may infer from repeated aggregates. HMAC control requests have timestamp/replay checks. The MTD secret is optional; without it, scheduling is reproducible and not secret.

## 6. Remaining limitations

No full CNN Flower round, cross-host deployment, independently administered party test, multi-seed benchmark matrix, complete poisoning/label-flip/sign-flip evaluation, secure private detector, production norm clipping, or MPC-BCD exists. MAC-failure, malicious party, dropout, and network partition injection were not performed. Runtime security of deployment certificates and key lifecycle has not been externally audited.

## 7. Claims that must NOT appear in the thesis

Do not claim full-model secure aggregation works; do not call 100k a universal protocol limit; do not claim cross-host validation, dropout recovery, differential privacy, private robust screening, secure clipping, MPC-BCD, measured poisoning resistance, production security certification, or prevention of aggregate-differencing inference. Do not present compiler-only full-shape results as runtime success.

## 8. Recommended thesis contributions

Frame the contribution as a research prototype integrating Flower with SPDZ2k weighted aggregation and round-scoped MTD scheduling, an evidence-backed control/security boundary, and a measured scalability study that identifies offline preprocessing as the bottleneck and quantifies an observed 100k completion point. Make the limitations and the absence of full CNN/attack validation part of the results, not footnotes.

## 9. Remaining work before submission

1. Obtain an adequately provisioned test environment and complete the full-size direct protocol run under a documented timeout.
2. Only after direct success, run a full CNN Flower round and verify the global state and coordinator visibility.
3. Validate independently hosted parties, SSL certificate/identity configuration, firewalling, and operational key handling.
4. Complete controlled multi-seed clean and attack experiments before making robustness claims.
5. Independently review MP-SPDZ v0.4.3 security parameter interpretation and add negative tests for MAC failure, malicious input count, party loss and network failure if those properties are to be claimed.
6. Prepare figures and tables from raw CSV/logs and have the supervisor approve the narrowed claims.

## 10. Overall readiness verdict

**NOT READY ? CRITICAL VALIDATION MISSING** for a final thesis claiming a full-model hybrid secure defense. Full-model direct execution and Flower integration are unverified; cross-host operation and attack mitigation evidence are missing. The implementation and current measurements are ready to support a scoped prototype/scalability chapter, provided all unsupported claims above are excluded. New MTD/round-identity regression coverage does not change the full-model or clipping status.
