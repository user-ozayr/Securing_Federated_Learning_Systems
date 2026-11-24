# Moving Target Defence: participation scheduling

## Mechanism

`MTDController` (`src/fl_security/mtd/controller.py`) chooses the cohort of
`K = int(N · fraction_train)` clients for every round. Randomness comes from a
round-scoped HMAC-SHA256 counter-mode PRF (`mtd/randomness.py`) with unbiased
rejection sampling (`randbelow`) and a partial Fisher–Yates shuffle (`sample`).

Schedules (`mtd.schedule`):

| Schedule | Round key | Properties |
|---|---|---|
| `static` | constant | same cohort (clients `0..K-1`) every round; fully predictable |
| `deterministic` | HMAC(SHA-256("fl-security-mtd-simulation-v1:" ‖ seed), round) | changes every round; reproducible from the public seed, therefore predictable by anyone who knows it; ignores `FL_MTD_SECRET` |
| `secret` | HMAC(HMAC(secret, "fl-security-mtd-rng-v1:" ‖ material), round) | changes every round; requires `FL_MTD_SECRET` (≥ 32 bytes); unpredictable without the secret |

Without `schedule`, the historical behaviour applies (`enabled` selects a
dynamic schedule; it is secret-derived whenever `FL_MTD_SECRET` is set).

Secret handling: the secret is read once by the coordinator, never sent to
clients or MPC parties, removed from the environment during the Flower
simulation, and never logged; runs record only `mtd_secret_seeded`. The
evaluation suite generates a fresh random secret per run and stores only its
SHA-256 commitment (`run_metadata.json`), so secret-schedule runs are
distributionally – not bit-for-bit – reproducible; supplying the same secret
reproduces a schedule exactly (tested).

## What MTD does and does not do

MTD changes **who participates**. It does not detect malicious clients: a
selected malicious client still submits a malicious update. Its security value
is against adversaries who exploit *predictable* participation – for example by
compromising (or activating) exactly the clients that will be selected.

## Adversary models (`mtd/exposure.py`)

The adversary knows the public configuration including the seed and predicts
the schedule by running the secret-free scheduler. With a budget of `b`
compromised clients:

* `random` – `b` uniformly random clients (no knowledge);
* `predictive` – the `b` clients with the most predicted participations;
* `just_in_time` – `b` members of each round's predicted cohort (an upper bound
  for adversaries that can target the next cohort).

## Measured exposure (Monte-Carlo, 200 trials, N = 12, K = 4, R = 10)

Source: `research_output/completion/experiments/mtd_exposure/`.

| b | schedule | adversary | compromise hit rate | mean malicious share | rounds with malicious majority |
|---|---|---|---:|---:|---:|
| 2 | static | just-in-time | 1.000 | 0.500 | 0.000 |
| 2 | deterministic | just-in-time | 1.000 | 0.500 | 0.000 |
| 2 | deterministic | predictive | 0.551 | 0.276 | 0.000 |
| 2 | secret | just-in-time | 0.331 | 0.166 | 0.000 |
| 2 | secret | predictive | 0.326 | 0.163 | 0.000 |
| 2 | secret | random | 0.328 | 0.164 | 0.000 |
| 3 | static | just-in-time | 1.000 | 0.750 | 1.000 |
| 3 | deterministic | just-in-time | 1.000 | 0.750 | 1.000 |
| 3 | secret | just-in-time | 0.333 | 0.250 | 0.020 |

Under the secret-derived schedule every adversary is reduced to the random
baseline (hit rate ≈ K/N); prediction accuracy is at chance (0.33). Against
static or seed-predictable schedules a just-in-time adversary converts its whole
budget into participants every round.

## Measured effect inside federated training (E3)

E3 runs FedAvg without a defence against a ×4 backdoor, with an adversary
budget of 2 and 3 seeds. Values are means ± 95 % t-interval half-widths
(`research_output/completion/experiments/summaries/key_results.md`).

| Schedule | Adversary | Malicious participants / round | Clean accuracy | Final ASR |
|---|---|---|---|---|
| static | predictive | 2.00 | 0.126 ± 0.103 | (model destroyed) |
| static | just-in-time | 2.00 | 0.112 ± 0.050 | (model destroyed) |
| deterministic | predictive | 1.20 ± 0.25 | 0.575 ± 0.255 | 0.51 ± 0.98 |
| deterministic | just-in-time | 2.00 | 0.133 ± 0.080 | (model destroyed) |
| secret | predictive | 0.70 ± 0.43 | 0.717 ± 0.165 | 0.54 ± 1.00 |
| secret | just-in-time | 0.90 ± 0.25 | 0.761 ± 0.050 | 0.51 ± 1.03 |

* **Exposure.** The secret-derived schedule cut predictive adversaries'
  exposure from two attackers in every cohort to 0.7–0.9 per round, and the
  model stayed usable.
* **No exclusion.** MTD did not prevent the backdoor once an attacker was
  selected (ASR ≈ 0.5); bounding a selected attacker's influence is the job of
  the in-MPC defence.
* **No benefit against non-predictive attackers.** In the core comparison (E1,
  three malicious clients that do not depend on prediction), randomised cohorts
  sometimes contained two or three boosted attackers. MTD alone was then
  *worse* than static participation, where one attacker sits in the cohort:
  * backdoor accuracy 0.317 (MTD only) and 0.413 (SPDZ2k + MTD), against 0.712
    for static participation.

  MTD is a defence against schedule prediction, not against poisoning.

## Interaction with the secure aggregation

The cohort is fixed before `start_round`; the SPDZ2k program binds the cohort
and server-known counts into its bytecode, so a client outside the cohort cannot
contribute. The adaptive defence threshold is computed over the cohort, so MTD
also changes which honest clients form the median in each round.

## Limitations

* MTD needs `N > K`; with full participation it has no effect.
* The schedule is only as unpredictable as the secret's confidentiality.
* Static participation also limits data coverage (only `K` clients ever train);
  comparisons of static vs dynamic participation therefore mix a security
  effect and a data-coverage effect. Study E3 isolates the security effect by
  comparing deterministic and secret dynamic schedules.
