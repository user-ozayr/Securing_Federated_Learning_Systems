# Final Validation Report

* **Repository and branch:** `fl-security-research-spdz2k-thesis`, branch
  `research/thesis-completion`.
* **Final code commit:** `e4c090a`.
* **Host:** aarch64 Ubuntu with 3 vCPU and 17 GiB RAM, running MP-SPDZ v0.4.3
  `spdz2k-party.x` and Python 3.11.18 (the existing `.venv311`).
* **Deployment:** all MPC parties, clients and the coordinator run on this one
  host.

All numbers are **measured**, except the estimates in §8, which are labelled as
such. Every value can be traced to a file in this directory; paths are
relative to `research_output/completion/`.

## 1. Scope

This report validates six things:
* (a) functional correctness of the code;
* (b) correctness of the secure computation against exact references;
* (c) protocol execution inside real federated training;
* (d) measured attack and defence effectiveness under the stated threat model;
* (e) overhead;
* (f) reproducibility from a fresh clone.

It does not validate security across independent hosts or trust domains (§11).

## 2. Automated tests

| Suite | Where | Commit | Result |
|---|---|---|---|
| default `pytest` | worktree | `e4c090a` | **131 passed, 1 skipped** (the opt-in MP-SPDZ test) – `test_results.txt` |
| real three-party MP-SPDZ integration test (`FL_RUN_MPSPDZ_TESTS=1`) | worktree | `e4c090a` | 1 passed (38 s) |
| default `pytest` | fresh clone | `99366f7` | 121 passed, 1 skipped |
| real MP-SPDZ integration test | fresh clone | `99366f7` | 1 passed (37 s) |
| default `pytest` | fresh clone | `e4c090a` | 131 passed, 1 skipped |

The 131 tests comprise the 77 tests that existed at the start (unchanged) and
54 new ones. Together with the opt-in integration test they cover:

* the exact reference against MPC semantics: wrap-around, signed comparisons,
  median, clipping search, output check and the weight-inverse trick;
* the party service: payload validation and program identity;
* attacks: scaled replacement, trigger and ASR, adaptive scaling, placements;
* MTD: explicit schedules and secret handling;
* dataset and model options;
* the robust Flower path: no tensors reach the coordinator, and a fail-closed
  abort keeps the completed rounds;
* the post-run analysis, which uses the recorded cohort only;
* the verdict rules of the attack/defence matrix.

## 3. SPDZ2k correctness: robust program vs exact reference (V)

The validation ran 13 scenarios with 3 local parties, d = 300, `f = 14` and
`g = 6`. Each scenario used K = 4 clients, except the 8-client collusion
scenario (K = 8). Every revealed value (threshold, clipped count, accept bits,
clip flags and all aggregate coordinates) was compared with `robust_reference`.

| Scenario | Bit-exact | Accepted | Output check | Expected | Note |
|---|---|---|---|---|---|
| clean_static_clip | yes | 1,1,1,1 | pass | pass | no clipping needed |
| scaled_replacement_static_clip | yes | 1,1,1,1 | pass | pass | norm-25 update clipped (coefficient 2/64) |
| boundary_static_clip | yes | 1,1,1,1 | pass | pass | norm 1.0, zero, 10⁻⁴, 1.5 |
| adaptive_clip_screen | yes | 1,1,1,0 | pass | pass | threshold = lower median 0.5; norm-10 update rejected |
| adaptive_screen_only | yes | 1,1,1,0 | pass | pass | screening without scaling |
| sample_weighted_clip | yes | 1,1,1,1 | pass | pass | weights 1,3,4,8 |
| malformed_out_of_range | yes | 1,1,1,0 | pass | pass | coordinate 2²⁷: invalid, excluded |
| wrap_large_coordinate | yes | 1,1,1,1 | **fail** | fail | coordinate 2⁴⁰ squares to 0; update rejected by the output check |
| malformed_negative_square | yes | 1,1,1,0 | pass | pass | squared norm wraps negative: excluded |
| wrap_single_attacker | yes | 1,1,1,1 | **fail** | fail | coordinate 2³² squares to 0; update rejected |
| inverse_weight_trick | yes | 1,1,1,1 | pass | pass | odd weight 3, visible norm 5 → clipped to w·τ = 2.97 |
| colluding_cancellation_k4 | yes | 1,1,1,1 | **fail** | (observed) | two colluders; aggregate norm 1.42 > 1 → rejected |
| colluding_cancellation_k8 | yes | all 8 | pass | (observed) | two colluders inject a norm-5.66 update with per-client bound 1.0 – **bypass**, aggregate norm 0.725 |

All 13 scenarios are bit-exact, and the output checks behave as analysed. The
k8 case demonstrates a limitation (colluding encoding-level attackers); it is
not a failure of the implementation.

Each scenario took 14–24 s end to end: about 6–10 s of protocol time and about
1.27 GB of loopback traffic. The same 13 scenarios were repeated from a fresh
clone with no reference mismatch and no unexpected output check
(`independent_validation/mpc_validation_fresh.log`). The benchmarks (§8) add 21
further robust rounds of up to 100,000 parameters, all bit-exact. Evidence:
`experiments/mpc_validation/`.

## 4. Correctness inside real federated rounds

Every instrumented run recomputes, in float64, the aggregate that its
configured aggregation should have produced. The input is the updates the
clients actually submitted; the result is compared with the update actually
applied to the global model. Sources:
* per round: `runs/<study>/<run>/round_analysis.csv`;
* summary: `experiments/summaries/end_to_end_reference_check.{csv,txt}`, produced
  by `tools/e2e_reference_summary.py`.

| Aggregation path | Runs | Rounds | Max. abs. error (healthy models) | Median per-run max. | Max. relative error |
|---|---:|---:|---|---|---|
| SPDZ2k robust program (all modes) | 70 | 700 | 2.4·10⁻⁷ | 1.2·10⁻⁷ | 2.0·10⁻⁷ |
| Plaintext execution of the same algorithm | 24 | 240 | 1.2·10⁻⁷ | 1.2·10⁻⁷ | 1.8·10⁻⁷ |
| SPDZ2k sum-only program | 36 | 324 | 9.5·10⁻⁷ | 2.4·10⁻⁷ | 9.1·10⁻⁷ |
| Plaintext FedAvg | 83 | 780 | 2.7·10⁻⁶ | 2.4·10⁻⁷ | 3.6·10⁻⁷ |
| Plaintext detector | 15 | – | no exact reference (its data-dependent decisions are not re-derived) | | |

Notes on the table:

* **Precision.** The applied update is the difference of two float32 models,
  and one float32 ulp at magnitude 1 is 1.2·10⁻⁷. Every path therefore agrees
  with its reference at float32 resolution, and all relative errors are below
  10⁻⁶.
* **Diverged models.** These are the 6 sum-only SPDZ2k runs and the 10 FedAvg
  runs under sign flip or strong boosts. Their absolute errors scale with the
  parameter magnitude (up to 1.6·10⁻² at |w| ≈ 2.8·10⁵ for SPDZ2k) and remain
  sub-ulp.
* **Output-norm check.** It never failed in any federated round.

Trajectory-level checks (`experiments/summaries/equivalence_checks.csv`):

* **SPDZ2k robust aggregation vs the plaintext execution of the same algorithm.**
  The runs compared are `e1x__smpc_defence__backdoor` and
  `e4__reference_defence__backdoor__default`, for both seed pairs (101, 102).
  The maximum per-round difference in accuracy, loss and ASR over all rounds is
  **0.0**: the secure computation reproduces the plaintext algorithm exactly
  inside federated training.
* **Determinism.** With no threshold published, the adaptive attacker falls back
  to the same ×4 scaling as the boosted backdoor. `e2__baseline__adaptive_backdoor`
  therefore reproduces `e1__baseline__backdoor` exactly for all three seeds.
* **Sum-only SPDZ2k vs plaintext FedAvg.**
  * *Original runs, S = 10⁶: the trajectories differ from round 1.*
    * Before the float32 cast, the fixed-point aggregate differs from float
      FedAvg by at most 10⁻¹⁰, which is below float32 resolution.
    * After the cast, 129–192 of the 2,202 parameters already differ by one ulp
      in round 1. 97 % of all such differences are values that lie exactly
      halfway between two float32 numbers, where the decimal scale rounds
      differently from float arithmetic.
    * SGD amplifies these differences. The recorded loss differs from round 1.
      The maximum |Δ accuracy| over 10 rounds was 0.010–0.017 without attack,
      and up to 0.19 (backdoor), 0.30 (label flip) and 0.51 (scaled
      replacement) under attacks that make training chaotic.
    * Diagnostic: `experiments/diagnostics/sum_only_divergence/`.
  * *Rerun with a power-of-two scale, S = 2⁴⁰ (all 36 sum-only runs).* All 18
    `smpc_only` runs equal the seed-matched FedAvg run in every recorded round
    (loss, accuracy, ASR):
    * 15 runs over all 10 rounds;
    * the 3 sign-flip runs up to their fail-closed abort.

    Sources: `experiments_pow2/pow2_vs_fedavg.csv` (`tools/pow2_vs_fedavg.py`).
    Provenance: `experiments_pow2/provenance.txt` lists the base commit and the
    SHA-256 of every changed file.

  Per-seed comparisons of `smpc_only` with `baseline` are therefore exact at
  S = 2⁴⁰. Comparisons of `smpc_mtd` with `mtd_only` remain statistical,
  because each run draws its own MTD secret and therefore its own cohorts.

## 5. Core comparison (E1)

**Setting:**
* Fashion-MNIST and a 2,202-parameter CNN;
* 12 clients, 4 per round, 10 rounds;
* 3 malicious clients, stratified placement (exactly one of them in the static
  cohort);
* attack strength ×4 for sign flip, scaled replacement and backdoor;
* seeds 101–103.

**Reported values:** mean ± half-width of the 95 % t-interval over the three
seeds. Accuracy is the mean of the last three rounds; ASR is taken at the final
round. Sources: `experiments/summaries/key_results.md`,
`attack_defence_matrix.csv`.

| Configuration | No attack | Label flip | Sign flip | Scaled replacement | Gaussian noise | Backdoor: accuracy | Backdoor: ASR |
|---|---|---|---|---|---|---|---|
| baseline (FedAvg) | 0.823 ± 0.027 | 0.690 ± 0.089 | 0.114 ± 0.061 † | 0.136 ± 0.114 † | 0.813 ± 0.020 | 0.712 ± 0.074 | 0.921 ± 0.218 |
| mtd_only | 0.830 ± 0.017 | 0.463 ± 0.098 | 0.099 ± 0.003 † | 0.179 ± 0.319 † | 0.806 ± 0.017 | 0.317 ± 0.672 | 0.306 ± 1.072 ‖ |
| smpc_only (SPDZ2k sum) § | 0.823 ± 0.027 | 0.690 ± 0.089 | 0.096 ± 0.019 †‡ | 0.136 ± 0.114 † | 0.813 ± 0.020 | 0.712 ± 0.074 | 0.921 ± 0.218 |
| smpc_mtd § | 0.824 ± 0.033 | 0.585 ± 0.571 | 0.247 ± 0.634 †‡ | 0.185 ± 0.324 † | 0.819 ± 0.005 | 0.494 ± 0.381 | 0.782 ± 0.475 |
| smpc_clip (static τ = 4) | 0.828 ± 0.023 | 0.766 ± 0.051 | 0.812 ± 0.034 | 0.760 ± 0.091 | 0.830 ± 0.009 | 0.816 ± 0.018 | 0.467 ± 0.165 |
| smpc_defence_mtd (full framework) | 0.830 ± 0.014 | 0.724 ± 0.386 | 0.821 ± 0.013 | 0.827 ± 0.017 | 0.817 ± 0.027 | 0.822 ± 0.014 | **0.017 ± 0.006** |

* † Model destroyed: accuracy is about 0.1, and the ASR of such a model is not
  meaningful.
* ‡ Includes fail-closed aborts. Five of the six sum-only SPDZ2k sign-flip runs
  stopped when the clients' fixed-point encoder refused the diverged model: all
  three `smpc_only` runs and two of the three `smpc_mtd` runs. At S = 2⁴⁰ the
  encoder's safe range is smaller, so they stopped after 1–2 rounds (2–4 at
  S = 10⁶). Their accuracy is that of the last completed rounds.
* § Rerun with the power-of-two scale S = 2⁴⁰ (`experiments_pow2/`; §4).
  * `smpc_only` equals `baseline` in every cell except sign flip, whose runs
    stop earlier (‡).
  * The original S = 10⁶ runs remain in `experiments/runs/e1/`. For
    `smpc_only` they gave 0.827 ± 0.028 without attack and a backdoor ASR of
    0.877 ± 0.223. For `smpc_mtd` they gave a backdoor ASR of 0.317 ± 1.254.
  * `smpc_mtd` differs between the two sets for two reasons: the rounding, and
    the cohorts, because each run draws a fresh MTD secret. With three seeds,
    the MTD rows therefore carry a large run-to-run variance.
  * `attack_defence_matrix.csv` still reflects the original runs.
* ‖ The ASR is low because the model was ruined in some seeds, not because the
  backdoor was mitigated; the matrix verdict is *not mitigated*.

Detection by the full framework (rejection inside MPC):

| Attack | Rejection TPR |
|---|---|
| Sign flip | 1.00 |
| Scaled replacement | 1.00 |
| Backdoor | 0.83 |
| Noise | 0.77 |
| Label flip | 0.44 |

The rejection FPR was **0.000 in all 18 runs**. About 36 % of honest
participations were *clipped*; clipping at the lower median does this by
construction.

The malicious share of the applied aggregate fell as follows:

| Configuration | Malicious share of the applied aggregate |
|---|---|
| Undefended | 0.41–0.62 |
| Static clipping | 0.31–0.35 |
| Full framework | 0.000 (sign flip, scaled replacement); 0.061 (backdoor); 0.070 (noise); 0.161 (label flip) |

Findings:

1. **No measurable clean-accuracy cost.** Without attack, every configuration
   reaches 0.823–0.830.
2. **SPDZ2k alone does not stop poisoning.** With the power-of-two scale,
   sum-only secure aggregation reproduces FedAvg exactly, including its
   failures (§4): backdoor ASR 0.92 in both, and scaled replacement and sign
   flip destroy the model. Under sign flip the diverging
   model was eventually refused by the fixed-point encoder and the secure round
   aborted. This is fail-closed behaviour: integrity is preserved but
   availability is lost.
3. **MTD alone is not a poisoning defence.** Against attackers that do not need
   to predict participation, random cohorts sometimes contain two or three
   boosted attackers. MTD-only and SMPC+MTD were *worse* than the static
   baseline under the backdoor (accuracy 0.317 and 0.494, model ruined in some
   seeds; SMPC+MTD from the S = 2⁴⁰ rerun, 0.413 at S = 10⁶).
4. **Secure static clipping (τ = 4) bounds magnitude attacks** (sign flip 0.812,
   scaled replacement 0.760) but only halves the backdoor (ASR 0.467): a clipped
   attacker keeps about a third (0.34) of the aggregate.
5. **The full framework mitigates every magnitude-based attack** without
   rejecting an honest client:
   * sign flip 0.821, scaled replacement 0.827, noise 0.817;
   * backdoor 0.822 with ASR 0.017, which equals the clean model's natural
     trigger response of 0.020.
6. **Label flipping is only partly mitigated.** Accuracy is 0.724 ± 0.386 (per
   seed 0.799, 0.545 and 0.828). Flipped-label updates are not much larger than
   honest ones, so screening rejects only 44 % of them. The rest are clipped
   (flag TPR ≥ 0.92) but still push in a harmful direction. This is the expected
   limit of norm-based defences.

## 6. Extended defences, adaptive attacker, sweeps, non-IID (E1x, E2, E4, E5)

**E1x – plaintext detector vs secure defences (static participation, 3 seeds).**

| Defence | Accuracy, no attack | Accuracy under sign flip / scaled replacement / backdoor | Backdoor ASR | Rejection TPR | Rejection FPR |
|---|---|---|---|---|---|
| Existing plaintext detector | 0.824 | 0.820 | 0.019 | – | – |
| Secure screening only | 0.827 | 0.818 | 0.022 | 1.00 | 0 |
| Secure clip+screen | 0.824 | 0.821 | 0.024 | 1.00 | 0 |

All three are *mitigated* by the matrix criteria. Accuracy is identical across
the three attacks because, with exactly one attacker per static cohort rejected
in every round, training proceeds on the same three honest clients. The secure
versions achieve this **without the coordinator seeing any individual update**.

**E2 – adaptive (constrain-and-scale) attacker, 3 seeds.** The attacker scales
its backdoor update to 0.95 × the published threshold, so it stays below the
screening bound.

| Defence | Rejection TPR | Clipped in | Malicious share of the aggregate | ASR (per seed) | Matrix verdict |
|---|---|---|---|---|---|
| Full framework | 0.00 | 30–70 % of its participations | 0.27–0.30 | 0.167 ± 0.388 (0.104, 0.053, 0.345) | partially mitigated |
| Static clipping | 0.00 | – | 0.33–0.34 | 0.304 ± 0.125 | partially mitigated |
| Plaintext detector | – | – | – | 0.019 | mitigated |

For comparison, the non-adaptive backdoor reached ASR 0.017 against the full
framework. The plaintext detector's thresholds are not the ones this attacker
targets. Staying just inside a published norm bound is the principal limitation
of norm-based defences against adaptive adversaries.

**E4 – sweeps (2 seeds).** These runs use the plaintext execution of the
adaptive defence (`reference_defence`), which is trajectory-identical to the
SPDZ2k program (§4), against FedAvg. Verdicts are taken against seed-matched
references from E1/E1x.

* **Backdoor boost.**

  | Boost | FedAvg | Defence |
  |---|---|---|
  | ×1 | ASR 0.38 | not rejected (TPR 0, within the honest norm range); clipping keeps ASR at 0.07/0.13 (mean 0.100): *partially mitigated* |
  | ×2 | ASR 0.89 | rejected (TPR 0.85); ASR 0.027 |
  | ×8 | model destroyed | rejected (TPR 1.00); ASR 0.024, accuracy 0.817 |
  | ×16 | model destroyed | rejected (TPR 1.00); ASR 0.024, accuracy 0.817 |

* **Sign-flip strength.**

  | Strength | FedAvg | Defence |
  |---|---|---|
  | ×1 | no attack effect | – |
  | ×2 | 0.700 | 0.806 (TPR 0.70) |
  | ×8 | destroyed | 0.817 (TPR 1.00) |

* **Number of malicious clients (1, 2, 4, 5 of 12).** With stratified placement
  and static participation, this gives **0, 1, 1 and 2 attackers in the fixed
  four-client cohort** (a design artefact: the sweep varies the in-cohort count
  only between 0 and 2).
  * m = 1 is therefore *no attack effect*.
  * With two attackers per cohort (m = 5), FedAvg was destroyed (0.141), while
    the defence kept 0.808 (TPR 1.00, ASR 0.022). The lower median of four norms
    is still an honest norm when two are inflated.
  * Three inflated norms out of four, which would move the median, were not
    tested.

**E5 – non-IID.**

* **Setting:** Dirichlet α = 0.5, sample-weighted robust aggregation with 2-bit
  weights and `g = 6`, secret MTD, 2 seeds.
* **Clean accuracy:** 0.783 (FedAvg) vs 0.788 (framework).
* **Backdoor, FedAvg:** accuracy 0.368 and 0.653, ASR 0.965 and 0.010 (the
  backdoor took hold in one seed).
* **Backdoor, framework:** accuracy 0.775 and 0.750, ASR 0.001 and 0.006,
  rejection TPR 1.00. Verdict *partially mitigated*: its own accuracy loss of
  0.025 exceeds the 0.02 tolerance.
* **First honest rejection.** Under non-IID data an honest client was rejected
  for the first time: rejection FPR 0.069 in seed 102, 0 in seed 101.
  Heterogeneous honest updates can exceed ρ·τ.

## 7. Moving Target Defence (E3-MC, E3)

Monte-Carlo exposure (200 trials, N = 12, K = 4, R = 10;
`experiments/mtd_exposure/`):
* Under the secret-derived schedule, the compromise hit rate is 0.33 (= K/N) for
  random, predictive and just-in-time adversaries, and prediction accuracy is
  0.33 (chance).
* Against static and deterministic schedules, a just-in-time adversary reaches a
  hit rate of 1.00; with b = 3 that means a malicious majority in every round.
* A predictive (fixed-set) adversary against the deterministic schedule reaches
  0.52–0.59 for R = 10 and 0.39–0.42 for R = 100.

FL runs (E3: FedAvg without defence, ×4 backdoor, adversary budget 2, 3 seeds):

| Schedule | Adversary | Malicious participants / round | Clean accuracy | Final ASR |
|---|---|---|---|---|
| static | predictive | 2.00 | 0.126 ± 0.103 | (model destroyed) |
| static | just-in-time | 2.00 | 0.112 ± 0.050 | (model destroyed) |
| deterministic | predictive | 1.20 ± 0.25 | 0.575 ± 0.255 | 0.51 ± 0.98 |
| deterministic | just-in-time | 2.00 | 0.133 ± 0.080 | (model destroyed) |
| secret | predictive | 0.70 ± 0.43 | 0.717 ± 0.165 | 0.54 ± 1.00 |
| secret | just-in-time | 0.90 ± 0.25 | 0.761 ± 0.050 | 0.51 ± 1.03 |

* The secret-derived schedule cut the predictive adversaries' exposure from 2.0
  to 0.7–0.9 malicious participants per round and kept the model usable.
* Predictable schedules let the adversary place two boosted attackers in every
  cohort and destroy the model.
* MTD did **not** prevent the backdoor once an attacker was selected (ASR about
  0.5 with large seed-to-seed variance); that requires the in-MPC defence (E1).
* E1's MTD-only results (§5) show the converse: against adversaries who do not
  depend on prediction, randomised cohorts alone do not help.

## 8. Overhead and scalability (B)

**Inside federated training** (E1, no attack, 2,202 parameters, K = 4, 3
parties; means over 3 runs × 10 rounds; `metrics/all_rounds.csv`):

| Configuration | Round time (s) | Start, incl. compilation (s) | Slowest client input (s) | Output wait (s) | MP-SPDZ protocol time (s) | Party traffic (MB) |
|---|---:|---:|---:|---:|---:|---:|
| FedAvg (plaintext) | 8.8 | – | – | – | – | – |
| SPDZ2k sum-only | 42.4 | 26.1 | 5.4 | 2.1 | 12.0 | 1,729 |
| SPDZ2k static clipping | 30.6 | 3.9 | 5.5 | 12.9 | 22.4 | 3,994 |
| SPDZ2k clip+screen (adaptive) + secret MTD | 32.5 | 4.4 | 5.7 | 14.2 | 23.9 | 4,291 |

* **Cost relative to FedAvg:** the full framework costs 3.7× the wall time per
  round on this host, and static clipping 3.5×.
* **Sum-only is slower in wall time.** The pre-existing weighted-sum program
  compiles for about 8.5 s per round, so its start phase dominates. Its protocol
  time is half that of the robust program.
* **Effect of MTD:** none on the cost.

**Controlled SPDZ2k benchmarks** (`benchmarks/benchmark_summary.md`; 35
attempts, 34 completed):

* **Linear scaling, constant comparisons.** Cost is linear in the model size.
  The robust circuit uses about 13 triples per coordinate (K = 4) against exactly
  5 for sum-only, and a d-independent comparison part (3,836 random bits).
* **Per-parameter cost.** From 50,000 parameters upwards:
  * robust round: about 5.9 ms and 1.26 MB per parameter;
  * sum-only round: about 2.5 ms and 0.53 MB per parameter.
* **100,000 parameters:** one robust round takes 592 s (sum-only 277 s). A
  sum-only round with 250,000 parameters was stopped by the parties' 600 s round
  timeout. Under the default timeout, the practical limit of this host is
  therefore about 100,000 parameters per robust round.
* **Two parties instead of three:** 1.77× faster protocol time and 3× less
  traffic.
* **Correctness:** all 21 robust benchmark rounds were bit-exact.
* **Extrapolation (estimate, not measured):** a robust round for the 2.12 M
  parameter CIFAR CNN would take about 3.4 h, about 2.7 TB of traffic and about
  18 GiB of party memory on this host. This is why the CIFAR model was not
  trained through SPDZ2k.

## 9. Independent reproduction (R)

Script: `independent_validation.sh`, run by `experiments/final_chain.sh`.
Outputs: `independent_validation/`.

**Setup:**
* Fresh clone of `research/thesis-completion` at `99366f7`
  (`/home/ubuntu/gemini/fresh_validation_clone_20261120T155117Z`), with no
  modified tracked files.
* Existing interpreter (`.venv311`, Python 3.11.18); nothing installed.
* Dataset files read from the original worktree (`FL_DATA_ROOT`).

**Results:**
* **Tests** – 121 passed and 1 skipped; the real MP-SPDZ integration test passed.
* **SPDZ2k validation** – 13 scenarios, all values identical to the exact
  reference, output checks as expected.
* **Deterministic re-runs.** Two suite runs were re-run from the clone with the
  same configuration and seed; only the output directory differed:
  * `e1x__smpc_defence__backdoor__s101` (SPDZ2k robust aggregation; executed in
    the suite at `f75eb7b`);
  * `e1__baseline__backdoor__s101` (plaintext FedAvg; suite commit `68f8970`).

  **All 11 evaluation rows were identical**: accuracy, loss, ASR, defence
  threshold, aggregate norm and accepted weight, plus the selected, malicious,
  accepted, rejected and clipped client sets (`rerun_comparison.txt`).
* **Import provenance.** The shared interpreter carries an editable install of
  the other worktree, and `fl_security` is a namespace package. A check
  (`tools/import_provenance_check.py`) therefore confirmed that in both the
  worktree and the clone every one of the 40 modules resolves to the tree under
  test. The three modules that exist only in the other tree (the superseded
  custom SMPC) are referenced nowhere (`import_provenance_*.txt`).
* **Final code commit.** A supplementary fresh clone at `e4c090a` passed
  131 tests (1 skipped) and the provenance check. Since `99366f7` only the
  post-run analysis and report tooling and their tests changed
  (`supplementary_clone_info.txt`).
* **Configuration consistency.** Every configuration of the 228 runs was
  regenerated from the final grid and matches the stored `config.yaml` and the
  recorded `config_sha256` byte for byte
  (`experiments/summaries/config_consistency_check.txt`).

**Limits of this reproduction:**
* It used the same host, interpreter and MP-SPDZ build. It shows that the
  committed code and recorded configurations reproduce the results; it does not
  show reproduction on other hardware or library versions.
* Secret-schedule runs cannot be reproduced without their secrets, which were
  never stored (only SHA-256 commitments).

## 10. Evidence handling and problems found during validation

1. **Failed attempts are archived, not deleted.** After the first suite pass, 21
   unfinished attempts were archived (`failed_attempts/20261120T122906Z/`):
   * 5 sum-only sign-flip runs that crashed before the fail-closed abort handling
     existed (`f75eb7b`);
   * 12 screen-only runs and 4 E5 runs whose configurations were *correctly
     rejected* by the margin and budget validation.

   All 21 were repeated. One later attempt, aborted in round 10 by a transient
   TLS-handshake reset (1 in 4,096 SPDZ2k client submissions), was moved to
   `failed_attempts/20261120T154646Z_infra/` and repeated.
2. **Configuration provenance.** The first suite process built configurations
   from the grid it had loaded at start-up, while each run executed (and
   recorded as `git_commit`) the code on disk. The grids differ only in the
   screen-only and E5 parameters; exactly those runs failed validation in pass 1
   and were repeated with the final grid. The configuration check in §9 confirms
   that every stored configuration equals the final grid.

   The four commits used by completed runs (`071fbbc`, `68f8970`, `f75eb7b`,
   `99366f7`) have identical experiment code paths for completed runs. The only
   change, in `f75eb7b`, is the abort path. No run was executed from a modified
   tree.
3. **Analysis contamination, found and fixed.**
   * The first pass archived failed attempts by copying them, and the repeats
     then reused the run directories.
   * In two aborted sum-only SPDZ2k runs with a secret schedule, per-client files
     of the earlier attempt (a different cohort) were mixed into the post-run
     analysis: 6–8 "participants" per round, and relative errors up to 1.1 that
     looked like aggregation errors.
   * `e4c090a` restricts the analysis to the cohort each run recorded and makes
     the suite move unfinished attempts aside. All runs were re-analysed.
   * Only these two runs changed: 15 stale entries were ignored, and their
     errors fell to 2–3·10⁻⁸ relative.
   * A snapshot of all derived files from before the fix is kept in the backup
     directory (`pre_cohort_fix_20261120T161015Z.tgz`, hash in `SHA256SUMS`).
   * In 15 repeated runs, a stale `*_abort.json` from the rejected first attempt
     was moved next to its identical archived copy
     (`failed_attempts/STALE_FILES_MOVED.txt`).
4. **Matrix verdict rule corrected.** The first version of the mechanical
   criteria counted a halved backdoor ASR as partial mitigation even when the
   model had been ruined; it labelled MTD-only and SMPC+MTD under the backdoor
   "partially mitigated". Since `e4c090a`, a halved ASR counts only if accuracy
   is not worse than the undefended baseline. Missing references are taken,
   seed-matched, from the study that shares the setting and are named in the
   matrix.
5. **Unreliable return codes in one log.** The return codes printed in
   `experiments/followup_chain.log` (`rc=0`) are the status of `date`, not of
   the suite or the benchmarks (a shell `$?` after command substitution). The
   outcome of each run and benchmark is in its own record.
6. **Orphaned processes.** Four idle party-service processes, orphaned by an
   early calibration run, were found and stopped before the final validation;
   they held no CPU.
7. **What is in git and what is not.** The repository's `.gitignore` excludes
   all logs (`*.log`), and the binary instrumentation archives (`*.npz`, about
   115 MB in 433 files) are excluded on purpose. Both remain on the research
   host. `final_validation_manifest.json`, which is committed, records the size
   and SHA-256 of every file in this directory, tracked or not. All configs,
   per-round CSVs, analyses, summaries, figures, metadata and reports are
   committed.

## 11. What is and is not established

**Established by this evidence**, in the stated setting (same-host deployment,
Fashion-MNIST, 12 clients with 4 per round, 10 rounds, 2–3 seeds):

1. **Correct secure computation.** The SPDZ2k robust program computes exactly
   the specified integer algorithm:
   * 13 adversarial validation scenarios (repeated from a fresh clone);
   * 21 benchmark rounds of up to 100,000 parameters;
   * inside federated training, 700 rounds at float32 resolution and
     trajectories identical to the plaintext execution.
2. **Update confidentiality against the coordinator.** By construction and by
   test, the coordinator receives in SMPC mode only the aggregate and the
   declared metadata: threshold, clipped count and accept bits, plus clip flags
   in the evaluation setting. This rests on the protocol and its tests; it is
   not an empirical measurement.
3. **Secure aggregation alone does not defend against poisoning.**
4. **A norm defence inside MPC does help.** It mitigated magnitude-based
   poisoning and a non-adaptive boosted backdoor in this setting without
   rejecting honest IID clients. It matched the plaintext detector while keeping
   individual updates hidden.
5. **Secret-derived MTD removes schedule predictability**, and in FL it reduced
   predictive adversaries' participation. MTD alone did not protect the model.
6. **Overhead is quantified**:
   * 3.5–3.7× FedAvg's round time at 2,202 parameters;
   * linear growth of cost with model size;
   * a practical limit of about 100,000 parameters per robust round on this host
     under the default round timeout.
7. **Reproducibility.** A fresh clone passes all tests and the validation
   scenarios and reproduces two experiments identically.

**Not established, and not claimed:**

1. Robustness against adaptive attackers that stay inside the published bound
   (E2: ASR up to 0.345), or against label flipping (partial only).
2. Robustness against colluding encoding-level attackers: the 8-client
   validation scenario shows a bypass, and per-coordinate range proofs are not
   implemented.
3. That SPDZ2k or MTD prevents poisoning by itself, or that MTD excludes
   malicious clients.
4. Security across independent hosts or trust domains, WAN performance, or
   availability. The protocol provides security with abort only; 5
   attack-induced aborts and 1 infrastructure abort were observed.
5. Differential privacy or resistance to inference attacks: neither is
   implemented.
6. Feasibility for large models: the CIFAR CNN is only extrapolated.
7. Small effects: with 2–3 seeds, differences below the 95 % interval widths
   cannot be resolved.
8. Median manipulation by three or more attackers in a four-client cohort
   (untested).

See `SECURITY_LIMITATIONS.md` for the full list.
