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
budget into participants every round. The effect on attack success inside real
FL training is measured in study E3 (`experiments/summaries`).

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
