# Moving-Target Defence Against Model Poisoning — Direction Screen, Cohort Bound and Paired Evaluation

Branch `research/mtd-defence` (worktree `fl-security-research-mtd-defence`, base
commit `14b7bb5`). Paths are relative to the repository root unless they start
with `experiments/`, which means `research_output/mtd_defence/experiments/`.

This study extends the secure aggregation framework of the main evaluation
(SPDZ2k + adaptive clip-and-screen + secret MTD cohorts, configuration
`smpc_defence_mtd`) with a second, moving-target check inside the MPC program,
and asks one question: **does the moving-target design reduce model poisoning,
and which part of it does the work?**

## 1. Summary

| Finding | Evidence |
|---|---|
| A moving threshold cannot separate a norm-adaptive attacker from honest clients: the attacker sits at 1.00 × T. | pilot, §3.1 |
| Sign agreement with the majority of the other clients separates direction-changing attackers (label flip, sign flip: AUC 0.98 with one attacker per cohort) and weakly separates stealthy backdoors (AUC 0.68–0.72). | pilot, §3.1 |
| The new SPDZ2k program (norm defence + direction screen on a secret coordinate subset) is bit-exact against its plaintext reference in all 20 validation scenarios and in every round of 15 FL runs. | V, F1, §4.1 |
| The secret 25 % screen costs about 6 × the norm defence per round (150 s vs 21 s protocol time; 29 GB vs 4.3 GB traffic at d = 2,202, K = 4). | B, §4.2 |
| With random per-run secrets and three seeds, MTD comparisons were dominated by cohort-draw luck; one earlier conclusion (M3: "MTD + screen is decisive against a just-in-time attacker") did not survive. | M3 vs F1, §5.3 |
| In the paired evaluation (same secret cohorts and subsets for every condition of a seed; 5 seeds) the full combination, with secret MTD cohorts and a secret direction screen, has the lowest mean backdoor success against every attacker. The per-seed sign counts favour it, but five seeds cannot establish significance at the 5 % level. | P3, §5.4 |
| Against an adversary that corrupts the clients it predicts will be selected, the secret schedule is what helps (ASR 0.98 → 0.65); the screen adds a further 0.08 on average (4 of 5 seeds). | P3, §5.4 |
| Honest cost: clean accuracy unchanged (0.833–0.835); honest rejection rate ≤ 2–5 %. | M2, P3, F1 |

## 2. Mechanism

### 2.1 Direction screen (implemented in `smpc/robust.py`, `smpc/programs/spdz2k_robust_aggregate.mpc`)

For a round with K clients and fixed-point updates x_k ∈ Z_{2^64}^d:

1. A coordinate subset S is selected with `HMACCounterRNG` from a round key
   `HMAC(secret, "direction-subset\0" ‖ round)`. `direction_subset` is
   `secret` (key from `FL_MTD_SECRET`), `public` (key from the public seed) or
   `all` (S = all coordinates); `direction_fraction` sets |S|/d.
2. Inside MPC: b_kj = [x_kj ≥ 0] for j ∈ S, computed as a 32-bit sign test
   (`less_than(0, bit_length=32)`). Valid inputs satisfy |x| ≤
   max_valid_norm · 2^14 = 2^20 < 2^31, so the 32-bit test equals the full
   test for every accepted input (checked by `test_sign_test_is_the_msb_of_the_low_32_bits`
   and the `direction_malformed_signs` scenario).
3. Majority of the others: m_kj = [2 · (Σ_i b_ij − b_kj) ≥ K − 1]; ties count
   as positive.
4. Agreement a_k = Σ_j [b_kj = m_kj]; the client is rejected if
   a_k < ceil(τ · |S|) (`direction_min_agreement` τ).
5. The rejection multiplies the client's acceptance bit of the norm defence
   (adaptive lower-median threshold T, clip to T, screen at ρ²·T). Only the
   aggregate, and the per-client flags if `reveal_client_flags` is set, are
   revealed.

The server sends `[min_agree, indices]` as two extra program arguments;
`validate_direction` rejects unsorted, duplicate, out-of-range or inconsistent
specifications on both sides of the party-control channel.

### 2.2 Evasive attacker (implemented in `attacks/byzantine.py`)

`evasive_backdoor` is the adaptive (norm-constrained) backdoor that also
trains a clean update and copies its clean values into the coordinates it
believes are checked: the true subset when it is public or `all`, otherwise a
random guess of `evasion_guess_fraction` = 25 % of the coordinates.

### 2.3 Paired evaluation (implemented in `experiments/suite.py`)

By default the suite draws a fresh `FL_MTD_SECRET` for every run, so two
conditions with the same seed face different secret cohorts and subsets. For a
study tagged `paired`, every run of (study, seed) receives
`HMAC(pairing_key, "paired-mtd-secret|study|seed")`; the 32-byte pairing key is
created once per output root (mode 0600) and only its SHA-256 is recorded. The
simulated adversary never sees the key, so the threat model is unchanged; only
the comparison becomes paired (common random numbers).
`tests/test_paired_secrets.py` checks that all MTD conditions of one seed draw
identical cohorts.

## 3. Pilot and design choices

### 3.1 Offline pilot on recorded E1 updates (`research_output/mtd_defence/pilot/`)

Per-client scores recomputed from the recorded updates of 175 runs of the main
evaluation (6,308 client participations); cohorts with one attacker:

| Attack | Sign-agreement AUC |
|---|---|
| label flip, sign flip | 0.98 |
| scaled replacement | 0.84 |
| adaptive backdoor | 0.72 |
| backdoor | 0.68 |

Honest agreement: median 0.61, 5th percentile 0.52. τ = 0.5 gives 2 % FPR,
τ = 0.52 gives 5 %. The norm-adaptive attacker's norm is 1.00 × T, so moving or
hiding the norm threshold cannot separate it (negative result; not pursued).
With two attackers among four clients the majority vote fails. Random cohorts
of 4 out of 12 clients with 3 attackers contain ≥ 2 attackers in about 24 % of
rounds.

### 3.2 Choice of τ and subset

M1 (τ = 0.5) produced no direction rejections for public or `all` subsets
against the backdoors, so M2 repeats all subset types at τ = 0.52. The secret
25 % subset at τ = 0.52 is used for the final framework (§5.1).

## 4. Correctness and cost of the secure version

### 4.1 Validation (`research_output/mtd_defence/mpc_validation/`)

Real three-party SPDZ2k runs of `spdz2k_robust_aggregate.mpc` against
`robust_reference`: 20 scenarios, 20 bit-exact, 0 unexpected output checks.
The seven new scenarios: honest clients, one sign-flipped client,
direction + norm rejection, malformed (wrap-around) sign inputs, all
coordinates, three clients with ties, K = 8 with two flipped clients. In the FL
runs of F1, every round's SPDZ2k aggregate matches the plaintext reference to
≤ 1.2 · 10⁻⁷ (float32 rounding of the decoded model;
`experiments/runs/f1/*/round_analysis.csv`).

### 4.2 Cost (`research_output/mtd_defence/direction_benchmark/`)

d = 2,202, K = 4, local parties, 2 repetitions, all bit-exact:

| Screen | Subset size | Protocol s (party 0) | End-to-end s | Global traffic | Communication rounds |
|---|---|---|---|---|---|
| none | 0 | 21 | 25 | 4.3 GB | 3,706 |
| secret 10 % | 220 | 70 | 75 | 14.2 GB | 12,200 |
| secret 25 % | 550 | 148 | 153 | 29.5 GB | 24,600 |

The compiled program needs 3,836 bits and 36,056 triples without the screen,
39,080 / 95,084 with 10 % and 91,888 / 183,540 with 25 %. In the F1 FL runs
(K = 7) one 10-round run takes 46 min on the 3-core aarch64 host, peak memory
7.7 GB.

## 5. Experiments

All plaintext-reference studies run the same algorithm as the SPDZ2k program
(`defences.norm_defence_reference`); F1 runs it inside SPDZ2k. Common setup:
Fashion-MNIST, compact CNN, 12 clients, IID, 10 rounds, 3 attackers
(`placement: stratified`) unless stated. ASR = backdoor success on triggered
test images after the last round; accuracy = mean clean accuracy over the last
three rounds; detection rates are per participation.

### 5.1 M1 / M2 / M2b — direction screen with static cohorts of K = 4

Mean ASR over seeds 101–103 (M2 at τ = 0.52; the norm-only baseline is M1
seeds 101–102 plus M2b seed 103):

| Attack | Norm defence only | All coordinates | Public 25 % | **Secret 25 %** | Secret 10 % |
|---|---|---|---|---|---|
| adaptive backdoor | 0.193 | 0.154 | 0.101 | **0.056** | 0.191 |
| evasive backdoor | 0.083 | **0.021** | 0.088 | 0.071 | 0.073 |
| label flip (rejection rate) | 0.77 | 0.93 | 0.93 | 0.93 | 0.90 |
| honest FPR, no attack | 0 % | 0 % | 0 % | 2.5 % | 5 % |

The secret 25 % subset is the only setting that keeps the adaptive backdoor
low on all three seeds (0.04–0.06); on seed 103, checking all coordinates or
10 % lets it grow to 0.42. Checking all coordinates is the only setting that
defeats the evasive attacker, because evasion then means sending a clean
update; secrecy of the subset helps against evasion only slightly (0.071 vs
0.088 public). Without `FL_MTD_SECRET` the secret subset is drawn per run, so
M1 and M2 differ for the same seed (by design).

### 5.2 M3 — cohort size bound K = 7 ≥ 2f + 1

Hypothesis: with K ≥ 2f + 1 every cohort has an honest majority, so random MTD
cohorts no longer let attackers dominate the median threshold or the majority
vote. Partly refuted: the honest majority holds, but the norm-adaptive
backdoor stays under T and is present in every static cohort (2 of 7), so the
norm defence alone reaches ASR 0.49 (it was 0.08–0.19 at K = 4). M3 used
unpaired secrets; its MTD comparisons are superseded by P3.

### 5.3 F1 — the final framework inside SPDZ2k (K = 7, 3 seeds)

`smpc_direction_mtd`: SPDZ2k + adaptive clip-and-screen + secret 25 % direction
screen (τ = 0.52) + secret MTD cohorts.

| Attack | ASR (range) | Accuracy | Attackers rejected | Honest FPR |
|---|---|---|---|---|
| none | 0.019 | 0.833 | — | 1 % |
| label flip | 0.022 | 0.833 | 88 % | 5 % |
| adaptive backdoor | 0.217 (0.02–0.60) | 0.822 | 30 % | 3 % |
| evasive backdoor | 0.153 (0.04–0.32) | 0.825 | 4 % | 3 % |
| just-in-time (4 corrupted) | 0.680 (0.59–0.83) | 0.810 | 4 % | 0 % |

**Correction.** M3 reported 0.217 for the same combination against the
just-in-time attacker and 0.628 for MTD alone. The screen rejected almost none
of those attackers (4 %), and F1 reaches 0.68 with the same algorithm, so the
M3 difference was the luck of the cohort draws, not the screen. This motivated
the paired design.

### 5.4 P3 — paired evaluation (K = 7, 5 seeds, `experiments/p3_paired.txt`)

Within a seed, both MTD conditions saw the same cohorts (identical attacker
participations per seed) and both screened conditions the same subsets. Seeds
101–103 of the static norm-only condition reproduce M3 bit for bit (12/12
runs).

Mean final ASR:

| Attack | Static, norm only | Static + secret screen | Secret MTD, norm only | **Secret MTD + secret screen** |
|---|---|---|---|---|
| adaptive backdoor | 0.493 | 0.314 | 0.239 | **0.132** |
| evasive backdoor | 0.177 | 0.085 | 0.143 | **0.067** |
| just-in-time (4 corrupted) | 0.979 | 0.979 | 0.651 | **0.568** |
| none | 0.020 | 0.020 | 0.019 | 0.018 |

Paired differences of the full combination (negative = lower ASR; seeds lower
/ higher, the rest tied):

| Attack | vs static norm only | vs static + screen | vs MTD norm only |
|---|---|---|---|
| adaptive backdoor | −0.36 (5 / 0) | −0.18 (4 / 1) | −0.11 (4 / 0) |
| evasive backdoor | −0.11 (4 / 1) | −0.02 (4 / 1) | −0.08 (2 / 0) |
| just-in-time | −0.41 (5 / 0) | −0.41 (5 / 0) | −0.08 (4 / 1) |

Clean accuracy: 0.833–0.835 without attack in every condition; under the
just-in-time attacker 0.662 with static cohorts and 0.816–0.819 with secret
cohorts. Honest rejection: mean ≤ 2.2 % per condition, at most 7.1 % in a
single run.

Interpretation:

- **Against an adversary that targets the schedule**, the secret schedule
  provides the protection: with a static schedule the adversary controls 4 of
  the 7 cohort members every round, and no robust aggregation rule survives a
  malicious majority (ASR 0.98, accuracy 0.66). The secret schedule reduces the
  adversary's participation from 40 to 22–27 over ten rounds.
- **Against stratified stealthy backdoors**, both moving parts contribute: MTD
  alone 0.49 → 0.24, the screen on top 0.24 → 0.13. Part of the MTD effect is
  lower exposure (17.8 vs 20 attacker participations over ten rounds: random
  cohorts contain 1.75 attackers on average, the stratified static cohort 2).
- **Statistical strength.** A one-sided sign test of 5/5 gives p = 0.031,
  4/4 (ties excluded) p = 0.0625; the comparisons against "MTD, norm only" do
  not reach 5 % with five seeds. The effects are consistent in direction but
  should be reported with their per-seed values.

## 6. Limitations

- The direction screen detects direction changes; norm-constrained backdoors
  are rejected only 10–35 % of the time, and an attacker that copies clean
  values into enough coordinates evades a 25 % secret subset (detection 4–13 %).
  Checking all coordinates defeats evasion but would cost roughly 4 × the 25 %
  subset (extrapolated from the linear growth in §4.2, not measured) and lets
  the adaptive backdoor through on some seeds.
- Majority-based checks fail when attackers are the majority of a cohort. MTD
  lowers the frequency of such cohorts against a targeting adversary but
  cannot exclude them.
- Five seeds, one dataset (Fashion-MNIST, IID), 12 clients, 10 rounds. The
  absolute ASR values depend on the seed (e.g. 0.33–0.66 for the static norm-only
  condition under the adaptive backdoor).
- Static cohorts with stratified placement are a favourable case for the
  defender at K = 4 (exactly one attacker per round) and an unfavourable one at
  K = 7 (two every round).
- The secret subset and schedule rely on the confidentiality of
  `FL_MTD_SECRET`; an attacker who learns it reduces the screen to the
  `public` case (M2: evasive ASR 0.088).
- Parties run on one host; the cost figures exclude network latency.

## 7. Reproduction

```bash
cd fl-security-research-mtd-defence
export PYTHONPATH=$PWD/src FL_MPSPDZ_HOME=/path/to/MP-SPDZ-v0.4.3 \
       FL_DATA_ROOT=/path/to/data OMP_NUM_THREADS=1
python -m pytest -q tests                                        # 159 passed, 1 skipped
python run_mpc_validation.py --output-dir research_output/mtd_defence/mpc_validation
python research_output/mtd_defence/tools/direction_benchmark.py research_output/mtd_defence/direction_benchmark
OUT=research_output/mtd_defence/experiments
python run_suite.py --output-root $OUT --studies m1 m2 m2b m3 p3   # plaintext reference, ~10 h
python run_suite.py --output-root $OUT --studies f1 --timeout 7200 # SPDZ2k, ~12 h
python analyze_suite.py --root $OUT --reanalyze
for s in m1 m2 m2b m3 p3 f1; do python research_output/mtd_defence/tools/m1_summary.py $OUT $s; done
python research_output/mtd_defence/tools/p3_paired_summary.py $OUT
```

Provenance snapshots (base commit, modified files with SHA-256, full diff) of
each stage: `research_output/mtd_defence/provenance*.txt` and `.diff`.
