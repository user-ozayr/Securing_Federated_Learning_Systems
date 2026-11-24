# Experimental methodology

All definitions are executable: `src/fl_security/experiments/grid.py` builds every
run configuration; `run_suite.py` executes them; `analyze_suite.py` aggregates.
Each run stores its YAML configuration, raw log, per-round CSV, post-run
analysis, packed instrumentation and metadata (git commit, config hash, timing,
MTD-secret commitment).

## Common setting

| Item | Value | Rationale |
|---|---|---|
| Dataset | Fashion-MNIST (60k train / 10k test), torchvision normalisation | public, harder than MNIST |
| Model | `CompactCNN`, 2,202 parameters | keeps a full SPDZ2k round with the defence at ≈ 32 s on the host. The 2.12 M CIFAR CNN is infeasible for multi-round MPC: at 100,000 parameters one round took 277 s (sum-only) and 592 s (robust) in the benchmarks |
| Clients | N = 12, IID equal partitions (5,000 samples each) | equal partitions make uniform and sample weighting identical |
| Participation | K = 4 per round (`fraction_train = 0.34`) | leaves room for MTD |
| Training | 10 rounds, 1 local epoch, SGD (lr 0.05, momentum 0.9), batch 32 | calibrated: 0.83 clean accuracy after 6 rounds |
| Malicious clients | b = 3 (25 %), **stratified placement** | the static cohort (clients 0–3) holds exactly one malicious client, the population's expected share, so static and dynamic participation face the same expected exposure |
| SPDZ2k | 3 parties, same host, `-R 64`, s = 64 | established configuration |
| Seeds | 101, 102, 103 (paired across conditions) | same partitions, malicious sets and local-training seeds per seed |

## Conditions (E1 core, required table)

| ID | Condition | FL | SPDZ2k | Secure defence | MTD |
|---|---|---|---|---|---|
| baseline | FedAvg | ✓ | – | – | static |
| mtd_only | FedAvg + secret MTD | ✓ | – | – | secret |
| smpc_only | sum-only SPDZ2k | ✓ | ✓ | – | static |
| smpc_mtd | sum-only SPDZ2k + MTD | ✓ | ✓ | – | secret |
| smpc_clip | SPDZ2k + secure clipping, static public bound τ = 4.0 | ✓ | ✓ | clip | static |
| smpc_defence_mtd | SPDZ2k + adaptive clip+screen + MTD (full framework) | ✓ | ✓ | clip+screen | secret |

Extended (E1x): `plaintext_robust` (existing plaintext detector, reference),
`smpc_defence` (full defence, static participation – isolates MTD),
`smpc_screen` (screening only). Adaptive defence parameters: lower-median
threshold (λ² = 1), clamp [0.25, 16], reject above 2× threshold (ρ² = 4),
`f = 14`, `g = 8`, uniform weights, per-client flags revealed for evaluation.

## Attacks

| Attack | Adversary capability | Strength | Target | Metric |
|---|---|---|---|---|
| none | – | – | – | clean accuracy |
| label_flip | train on `y → (y+1) mod 10` | all local data | untargeted | accuracy degradation |
| sign_flip | submit `−4·Δ` | ×4 | untargeted | accuracy degradation |
| scaled_replacement | label-flip training, update ×4 (≈ K, model replacement) | ×4 | untargeted | accuracy degradation |
| random_noise | add N(0, 0.2²) per parameter (‖noise‖ ≈ 9.4) | σ = 0.2 | untargeted | accuracy degradation |
| backdoor | 4×4 white trigger, 50 % of each batch relabelled to class 0, update ×4 | ×4 | trigger → class 0 | ASR (non-target test images), clean accuracy |
| adaptive_backdoor (E2) | backdoor, update rescaled to 0.95 × the published threshold | at the bound | trigger → class 0 | ASR under each defence |

ASR is measured only on test images whose true class is not the target, after
stamping the trigger; it is reported separately from clean accuracy. For runs
without a backdoor the same measurement gives the clean model's natural trigger
response (reference level).

## Further studies

* **E2 adaptive attacker** against full defence, static clipping, FedAvg and the plaintext detector.
* **E3 MTD predictability**: FedAvg with a backdoor attacker (budget 2) that
  compromises clients it predicts will be selected (`predictive`, `just_in_time`)
  under static, deterministic and secret schedules; complemented by the
  training-free Monte-Carlo exposure study (`run_mtd_exposure.py`).
* **E4 sweeps** (2 seeds) for FedAvg and for the *plaintext reference execution*
  of the adaptive defence (labelled `reference_defence`; identical integer
  algorithm, no cryptography). The sweep parameters are:
  * malicious count (1, 2, 4, 5 of 12);
  * backdoor boost (1, 2, 8, 16);
  * sign-flip strength (1, 2, 8).

  Two reference runs at the default setting allow a direct comparison with the
  SPDZ2k runs of E1x. They are trajectory-identical to those runs. With
  stratified placement and static participation, the malicious counts put 0, 1,
  1 and 2 attackers into the fixed four-client cohort.
* **E5 non-IID** (2 seeds): Dirichlet α = 0.5, secret MTD, and sample-weighted
  robust aggregation with 2-bit weights and `clip_bits = 6`. These parameters
  keep the output-check margin; 3-bit weights violate it.

* **E6 update leakage** (`run_leakage_study.py`, outside the suite): a curious
  coordinator attacks either the target client's update (plaintext FedAvg) or the
  decoded SPDZ2k sum-only aggregate of the four-client cohort. The setting is one
  local SGD step on B ∈ {1, 2, 4, 8} images, an untrained and a one-epoch-trained
  model, and 8 trials per cell (seed 101). Three attacks are run:
  * optimisation-based inversion on CompactCNN, with the TV weight calibrated on
    seed 7;
  * the analytic read-out of CompactCNN's penultimate features;
  * the analytic read-out of input images through the first layer of a probe MLP.

  Scores are SSIM/PSNR or cosine similarity of the best match to each of the
  target's images. Unlike the suite runs, E6 ran from an uncommitted tree; each
  shard's metadata records the SHA-256 of every source file. Details:
  `research_output/completion/experiments/leakage/README.md`.


## Metrics

Per round (CSV): clean accuracy and loss, ASR, selected/malicious clients,
defence threshold, accepted/rejected/clipped clients, output-check result,
detection counts, round wall time, MPC start/input/output/finish times,
MP-SPDZ-measured protocol seconds and global traffic, application-level input
bytes. Post-run analysis (instrumentation): applied update norm, deviation from
the honest-only FedAvg update, malicious contribution share before/after the
defence, and the maximum difference between the applied update and the exact
reference (end-to-end correctness of the secure path).

Detection: rejection TPR/FPR and flag (reject or clip) TPR/FPR over all
participations. Overhead: per-round wall time, MPC protocol time, traffic, and
the isolated SPDZ2k benchmarks (`run_mpc_benchmark.py`).

## Statistics

Mean, sample standard deviation and two-sided 95 % Student-t intervals over
seeds; paired per-seed differences against `baseline` under the same attack.
With three seeds the intervals are wide; they are reported as measured and no
significance claims are made beyond them.

## Controls and threats to validity

* All runs share data, partitions and seeds per seed. Each run records the
  commit it executed (`git_commit`; no run used a modified tree).
  * The completed runs used `071fbbc`, `68f8970`, `f75eb7b` or `99366f7`. Their
    experiment code paths are identical for completed runs: only the abort path,
    grid parameters of runs that were repeated, and post-run tooling changed.
  * Every stored configuration equals what the final grid generates
    (`tools/verify_run_configs.py`).
  * A running suite keeps the grid it loaded at start-up, so restart the suite
    after changing `grid.py`.
* Failed attempts are archived with their reason under `failed_attempts/` and
  repeated; nothing is deleted. Since `e4c090a`, the suite moves an unfinished
  attempt aside before repeating it, and the post-run analysis uses only the
  cohort the run recorded.
* Per-round wall time compares implementations, not only protocols:
  * the pre-existing sum-only program compiles for about 8.5 s per round, so its
    rounds are slower than the robust ones although its protocol time is half;
  * MP-SPDZ's own protocol time and traffic are therefore reported separately.
* Static participation also restricts data coverage to four clients; E3
  separates the scheduling security effect using dynamic schedules only.
* Timing: the suite runs one experiment at a time on a 3-core host; MPC
  benchmarks were run separately on an otherwise idle host. Short development
  activity during the suite may perturb individual round timings slightly.
* Same-host MPC: performance reflects loopback networking and CPU contention
  between parties, not a WAN deployment.
* The adaptive attacker is assumed to know the threshold (worst case); the
  defence publishes it each round in the current design.

## Results

Measured results, the attack/defence matrix (with its mechanical criteria) and
all limitations are in `research_output/completion/`:
* `FINAL_VALIDATION_REPORT.md`;
* `attack_defence_matrix.csv`;
* `experiments/summaries/`;
* `SECURITY_LIMITATIONS.md`.

## Historical evidence status (before 2026-11-20)

The earlier integrated Flower run was a same-host, one-round smoke test with a
synthetic 8-parameter model; direct production-circuit profiling completed up to
100,000 parameters (246 s) and a 250k run reached a 300 s watchdog. Those
records remain in `research_output/archive/early_phase_2026-11-18/runtime_optimization/` and
`research_output/archive/early_phase_2026-11-18/scalability_phase/` and are not re-labelled.
