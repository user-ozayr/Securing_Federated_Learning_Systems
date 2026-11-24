# Final federated learning security validation

**Run:** `research_output/final_validation_20261119T194946Z/`  
**Repository:** `fl-security-research-spdz2k-thesis`  
**Branch / commit:** `research/spdz2k-thesis` / `5c7b4978a8d1c7f54f03cce28d5498b5ee3fef4c`

## Results

- **Automated tests:** 77 passed, 0 failed (5.29 seconds); two upstream deprecation warnings.
- **Adversarial testing:** 3 attack families exercised at limited scope (sign flip and random noise on synthetic vectors; label flip transform), with sign flip also used in the fresh integrated pipeline across two rounds. This is not a comprehensive model attack efficacy evaluation.
- **Defense evidence:** 4 bounded defense behaviors validated (local SPDZ2k execution, secret-seeded MTD selection, control authentication/replay rejection, and synthetic plaintext robust filtering); 3 areas remain partial (malformed-input coverage, broad MPC/plaintext correctness comparison, and robust filtering integration); 1 poisoning-resistance claim fails because the secure sum accepts malicious contributions. Robust screening cannot be combined with sum-only SMPC.
- **MPC vector sizes completed:** historical same-host protocol runs passed at 8, 1,000, 10,000 (corrected retry), 50,000, and 100,000 parameters. An earlier 10,000 run failed with `unexpected data length`; 250,000 aborted at its 300-second cap. A separate compile-only scaling table reaches 2,122,187 parameters.
- **Integrated Flower:** fresh two-round, three-client/three-party local run passed with secret-seeded MTD and sign-flip contributions. It used a tiny synthetic model/data set and same-host parties. It is not cross-host or full-model validation.
- **Full-model aggregation:** not demonstrated. The successful protocol runs are vector benchmarks; the integrated Flower run uses a small linear model.
- **Build/package:** not validated in this environment; `uv` and pip are unavailable and `python -m build --wheel` has no executable build frontend.
- **Thesis readiness:** implementation and bounded local evidence are suitable to describe with strict scope. Claims of poisoning resistance, cross-host security, production readiness, differential privacy, clipping, or full-model runtime are not supported.

The 24-row attack/defense matrix records 8 PASS, 11 PARTIAL, 1 FAIL, and 4 NOT TESTED findings.

## Critical gaps

The sum-only MPC circuit does not screen malicious client contributions. Selected sign-flip updates were accepted by the integrated run; the tiny test accuracy remained 0.75, without a baseline or attack success metric. Label-flip/noise/backdoor effectiveness, malformed-client injection into the live integrated path, cross-host operation, and full-model completion remain untested. No fixes were made because this run did not confirm an implementation defect.

See `ATTACK_DEFENSE_MATRIX.csv`, `THESIS_CLAIM_VERIFICATION.md`, and `SECURITY_GAP_ANALYSIS.md` for scope and evidence.
