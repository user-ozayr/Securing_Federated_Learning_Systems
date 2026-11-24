# Thesis Objective Traceability — "Securing Federated AI Systems"

Each official objective is mapped to the implemented component, source files,
tests, experiment identifiers, evidence files, measured findings and remaining
limitations. Source paths are relative to the repository root
(`fl-security-research-spdz2k-thesis`); evidence paths are relative to
`research_output/completion/`.

Experiment IDs: **V** SPDZ2k validation scenarios; **E1** core six-configuration
comparison; **E1x** extended defences; **E2** adaptive attacker; **E3** MTD
predictability in FL; **E3-MC** MTD Monte-Carlo exposure; **E4** proportion and
strength sweeps; **E5** non-IID; **E6** update leakage (gradient inversion
against the plaintext and the SPDZ2k view); **B** SPDZ2k benchmarks; **R**
fresh-clone reproduction.

## Objective 1 — Survey and classify attacks

| Item | Evidence |
|---|---|
| Component | attack library and threat model |
| Source | `src/fl_security/attacks/byzantine.py`, `attacks/backdoor.py`, `attacks/label_flip.py`, `attacks/sign_flip.py`, `attacks/gradient_inversion.py`, `mtd/exposure.py`, `experiments/leakage.py` |
| Classification | `THREAT_MODEL.md` (adversary table: curious coordinator, malicious parties, training-level and encoding-level malicious clients, colluding clients, predictive adversary, adaptive attacker); `docs/experimental_methodology.md` (attack table with capability, strength, target, metric) |
| Implemented attacks | model poisoning (sign flip, scaled model replacement, Gaussian noise), data poisoning (label flip, BadNets backdoor), adaptive constrain-and-scale backdoor, schedule-aware (predictive, just-in-time) compromise, encoding-level wrap-around attacks (V); inference by a curious coordinator: optimisation-based gradient inversion, analytic feature and input read-out through fully connected layers, label read-out (E6) |
| Tests | `tests/test_attacks.py`, `test_byzantine.py`, `test_attack_integration.py`, `test_attacks_extended.py`, `test_mtd_schedules.py`, `test_gradient_inversion.py` |
| Experiments | E1, E2, E3, E4, E6, V |
| Not covered | membership and property inference (classified in the threat model, not implemented); gradient inversion of multi-step local updates; a malicious coordinator that manipulates the model to isolate clients |

## Objective 2 — Evaluate defences and their limits against adaptive adversaries

| Item | Evidence |
|---|---|
| Components | plaintext robust detector (existing), secure clipping, secure screening, combined adaptive defence, output-norm check |
| Source | `federated/robust_aggregation.py`, `smpc/programs/spdz2k_robust_aggregate.mpc`, `smpc/robust.py` |
| Tests | `test_robust_aggregation.py`, `test_robust_reference.py`, `test_flower_robust_path.py` |
| Experiments | E1x (plaintext detector vs secure defences), E2 (adaptive attacker), V (weight-inverse and colluding wrap-around attacks), E4 (strength/proportion sweeps) |
| Limits identified | within-bound attacks; colluding encoding-level attackers exceed per-client bounds (V `colluding_cancellation_k8`); median manipulation by ≥ K/2 attackers; adaptive attacker at the bound (E2) |

## Objective 3 — SMPC to protect model updates during aggregation

| Item | Evidence |
|---|---|
| Component | MP-SPDZ v0.4.3 SPDZ2k (3 parties, Z_2^64, s = 64): sum-only and robust programs, authenticated party control |
| Source | `smpc/mp_spdz.py`, `smpc/mp_spdz_party_service.py`, `smpc/programs/*.mpc`, `smpc/local_demo.py` |
| Tests | `test_mp_spdz.py`, `test_mp_spdz_control.py`, `test_security_hardening.py`, `test_party_service_robust.py`, `test_flower_secure_smoke.py`, opt-in `test_mpspdz_integration.py` |
| Experiments | V, E1 (`smpc_only`, `smpc_mtd`, `smpc_clip`, `smpc_defence_mtd`), B, E6 (what the coordinator can reconstruct with and without SPDZ2k) |
| Evidence | `experiments/mpc_validation/`, per-run `round_analysis.csv` (`reference_max_abs_error`), `benchmarks/`, `experiments/leakage/` |
| Limits | same-host parties; security with abort; output client trusted with the aggregate; the aggregate of a small cohort can still contain exact copies of individual training images (E6) |

## Objective 4 — Moving Target Defence

| Item | Evidence |
|---|---|
| Component | HMAC-SHA256 round-scoped schedules: static, deterministic, secret |
| Source | `mtd/controller.py`, `mtd/randomness.py`, `mtd/client_selection.py`, `mtd/exposure.py`, `mtd/simulation.py` |
| Tests | `test_mtd.py`, `test_mtd_execution.py`, `test_mtd_committee_privacy.py`, `test_mtd_schedules.py` |
| Experiments | E3-MC (200 trials × 3 schedules × 3 adversaries × 3 budgets), E3 (FL with predictive adversaries), E1 (`mtd_only`, `smpc_mtd`, `smpc_defence_mtd`) |
| Evidence | `experiments/mtd_exposure/`, `docs/mtd_scheduling.md` |
| Limits | MTD does not exclude a selected malicious client; depends on secret confidentiality |

## Objective 5 — Hybrid framework

| Property | Mechanism | Evidence |
|---|---|---|
| Model-update confidentiality | SPDZ2k; no tensors to the coordinator in SMPC mode | `test_flower_secure_smoke.py`, `test_flower_robust_path.py` (empty parameter lists), V |
| Aggregation integrity | SPDZ2k MACs, bytecode agreement, count binding, output-norm check | existing control tests; V; per-run reference error |
| Resilience against poisoning | in-MPC clipping/screening with adaptive threshold | E1, E1x, E2, E4 |
| Privacy | only aggregate + declared metadata revealed | `docs/secure_robust_aggregation.md` §7 |
| Resistance to predictable participation | secret-derived MTD | E3-MC, E3 |
| Entry point | `run_experiment.py` with `smpc.defence` + `mtd.schedule: secret` (configuration `smpc_defence_mtd`) | `FINAL_ARCHITECTURE.md` |

## Objective 6 — Reproducible evaluation

| Item | Evidence |
|---|---|
| Runner | `run_suite.py` (process isolation, timeouts, resumable), `analyze_suite.py` |
| Records | per-run `config.yaml`, `run.log`, `*_results.csv`, `round_analysis.csv`, `instrumentation.npz`, `run_metadata.json` (commit, config hash, secret commitment, timings) |
| Metrics | clean accuracy/loss per round, ASR, malicious participation, influence shares, deviation from honest FedAvg, detection TPR/FPR, round time, MPC protocol time and traffic, input bytes |
| Statistics | mean, std, 95 % t-intervals over seeds; paired differences |
| Overhead | E1 per-round costs; B (sizes 1k–250k, sum-only vs robust variants, 2 vs 3 parties) |
| Reproduction | `experiments/reproduction_commands.md`, R |
| Evidence checks | `tools/verify_run_configs.py` (228/228 configurations equal the final grid), `tools/e2e_reference_summary.py`, `tools/import_provenance_check.py`, `tools/raw_log_index.py`, `final_validation_manifest.json` |
| Tests | `test_analysis_cohort.py`, `test_report_matrix.py`, `test_statistics.py` |

## Measured findings per objective

All values are measured; details and intervals are in `FINAL_VALIDATION_REPORT.md`.
Accuracy is the mean of the last three rounds over three seeds, unless stated
otherwise.

**Objective 1 – survey and classify attacks.**
* *Status:* achieved for poisoning and for update leakage to a curious
  coordinator (E6). Membership and property inference are classified in the
  threat model only.
* *Findings* (E1, FedAvg, 3 seeds):

  | Attack | Effect on FedAvg |
  |---|---|
  | Sign flip | model destroyed (0.114) |
  | Scaled replacement | model destroyed (0.136) |
  | Backdoor | ASR 0.921, while clean accuracy only fell to 0.712 |
  | Label flip | −0.13 accuracy |
  | Gaussian noise | no measurable effect |

  Schedule-aware adversaries placed two attackers in every cohort under
  predictable schedules (E3), and encoding-level wrap-around attacks were
  executed against SPDZ2k (V).

**Objective 2 – defences and their limits against adaptive adversaries.**
* *Status:* achieved, including negative results.
* *Findings:*
  * E1x: the plaintext detector, secure screening and secure clip+screen all
    mitigate sign flip, scaled replacement and the backdoor (accuracy
    0.818–0.821, ASR 0.019–0.024).
  * E1: static clipping only halves the backdoor (ASR 0.467).
  * E2: an adaptive attacker at 0.95 × the threshold is never rejected and
    reaches ASR 0.167 against the full framework and 0.304 against static
    clipping.
  * E1: label flipping is only partly mitigated (0.724).
  * V: colluding encoding-level attackers bypass the per-client bound (k = 8).
  * E5: under non-IID data an honest client was rejected (FPR 0.069 in one
    seed).

**Objective 3 – SMPC to protect model updates during aggregation.**
* *Status:* achieved on a single host.
* *Correctness:* SPDZ2k (3 parties) runs in every secure round of 106 runs. It
  is bit-exact against the exact reference in 13 adversarial scenarios and 21
  benchmark rounds. End-to-end error inside FL is ≤ 2.4·10⁻⁷ over 700 robust
  rounds, and trajectories are identical to the plaintext execution of the same
  algorithm. With the power-of-two fixed-point scale (S = 2⁴⁰), sum-only
  SPDZ2k is trajectory-identical to plaintext FedAvg in all 18 `smpc_only`
  runs (`FINAL_VALIDATION_REPORT.md` §4, `experiments_pow2/`).
* *Overhead:* 3.5–3.7× FedAvg's round time at 2,202 parameters, and about
  5.9 ms and 1.26 MB per parameter for the robust round (B). The limit is about
  100,000 parameters per round under the default 600 s round timeout.
* *Negative result:* SPDZ2k alone gives no poisoning resistance; under the
  backdoor, smpc_only has ASR 0.877 against FedAvg's 0.921.
* *Leakage (E6, FedSGD, K = 4):* hiding individual updates removes label
  attribution (precision 1.00 → 0.29–0.71) and most multi-image
  reconstructions. Through a fully connected first layer, however, the aggregate
  still yields near-exact copies of 75–100 % of a client's images at B = 1,
  against 100 % from the individual update, and 3–28 % at B = 8. Secure
  aggregation over a small cohort is therefore not a privacy guarantee for the
  training data.

**Objective 4 – Moving Target Defence.**
* *Status:* achieved for unpredictability. MTD is not a poisoning defence.
* *Exposure without training (E3-MC):* under the secret-derived schedule the
  compromise hit rate is 0.33 (= K/N) for every adversary, against 1.00 for a
  just-in-time adversary facing a static or deterministic schedule.
* *In FL (E3):*

  | Schedule | Malicious participants / round | Accuracy |
  |---|---|---|
  | Secret | 0.7–0.9 | 0.72–0.76 |
  | Predictable | 2.0 | 0.11–0.13 |

* *Negative result (E1):* against attackers that do not need prediction, MTD
  alone was worse than static participation (backdoor accuracy 0.317).

**Objective 5 – hybrid framework.**
* *Status:* achieved within the stated threat model.
* *Findings:* the full framework (secure adaptive clip+screen inside SPDZ2k plus
  the secret MTD schedule) gave:

  | Attack | Accuracy | Notes |
  |---|---|---|
  | Sign flip | 0.821 | |
  | Scaled replacement | 0.827 | |
  | Noise | 0.817 | |
  | Backdoor | 0.822 | ASR 0.017 |

  Clean accuracy is 0.830, the rejection FPR is 0 for IID clients, and the
  coordinator never receives an individual update.
* *Limits:* adaptive attackers, label flipping, colluding encoding attacks, and
  availability (security with abort).

**Objective 6 – reproducible evaluation.**
* *Status:* achieved.
* *Findings:*
  * 228 runs: 223 completed and 5 fail-closed aborts.
  * 3 seeds for the core studies and 2 for the sweeps and non-IID.
  * 95 % t-intervals, paired differences, and a mechanical attack/defence matrix
    with named, seed-matched references.
  * Every failed attempt is archived with its reason.
  * A fresh clone reproduces two experiments identically and passes all tests.
  * 228/228 configurations are consistent with the final grid.
  * A SHA-256 manifest covers every evidence file.
