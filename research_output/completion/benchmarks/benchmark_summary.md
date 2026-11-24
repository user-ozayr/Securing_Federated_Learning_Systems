# SPDZ2k Aggregation Benchmarks

All numbers in this file are **measured**, except section 6, which is an
explicitly marked extrapolation. Raw data: `benchmark_results.jsonl` (one record
per attempt, including the failed one), `benchmark_results.csv`, per-variant
aggregates `benchmark_summary.csv`, party logs `raw_logs/`. Driver output:
`../benchmarks_driver.log`. Harness: `src/fl_security/smpc/benchmark.py`,
`run_mpc_benchmark.py`.

## 1. Setup

* **Host:** aarch64 Ubuntu, 3 vCPU, 17 GiB RAM. All parties and the coordinator
  run on this one host and talk over loopback (TLS). MP-SPDZ v0.4.3,
  `spdz2k-party.x`, ring Z_2^64 (`-R 64`), SPDZ2k security parameter s = 64.
* **Isolation:** the benchmarks ran on 2026-11-20 between 14:03 and 14:55 UTC,
  after the experiment suite had finished and while no other experiment was
  running. A watchdog (1,800 s cap per case, 3 GiB memory floor, 2 GiB disk
  floor) was never triggered.
* **Workload:** each record is one complete secure round with K = 4 synthetic
  clients. The client updates have random directions and norms 0.5, 0.75 and 1.0,
  plus one oversized update with norm 6.0, which exercises rejection or clipping.
* **Programs:**
  * *Sum-only* is the pre-existing SPDZ2k weighted-sum program (fixed-point scale
    10⁶, chunks of 1,024 values).
  * *Robust* is `spdz2k_robust_aggregate.mpc` with f = 14 and g = 8. The threshold
    is either static (τ = 1.0) or adaptive (lower median, λ² = 1, ρ² = 4, bounds
    0.05–4.0). Chunks hold 256 values and weights are uniform.
* **Repeats:**
  * 3 for the main sizes up to 10,000;
  * 2 for the variant and party-count cases;
  * 1 for 50,000 parameters and above.

  Table cells give the mean and, in brackets, the range.
* **Metrics:**

  | Metric | Definition |
  |---|---|
  | *Total* | Coordinator wall time for the whole round. |
  | *Start* | Concurrent start requests to all parties, including compilation and launch. |
  | *Input* | The 4 clients submitting one after another; the sum of their times. |
  | *Protocol* | MP-SPDZ's own `Time =`, maximum over parties. |
  | *Data* | MP-SPDZ's `Global data sent`: all parties, loopback, decimal MB. |
  | *Peak RSS* | Peak of the summed resident memory of **all** party processes, sampled every 0.25 s. |
  | *Triples / random bits* | From a compile-only pass of the identical circuit. |

## 2. Scaling with model size (3 parties, K = 4)

| Parameters d | Program | n | Total (s) | Protocol (s) | Data (MB) | Peak RSS, all parties (MiB) | Triples | Random bits | Result vs reference |
|---:|---|---:|---|---|---:|---:|---:|---:|---|
| 1,000 | sum-only | 3 | 18.2 [17.7–18.9] | 3.70 [3.43–4.09] | 605 | 921 | 5,368 | 252 | max abs error ≤ 1.05·10⁻⁸ |
| 1,000 | robust clip+screen, adaptive | 3 | 16.9 [16.8–17.0] | 12.7 [12.7–12.8] | 2,534 | 1,609 | 20,118 | 3,836 | bit-exact 3/3 |
| 2,202 | sum-only | 3 | 35.0 [34.5–35.4] | 8.75 [8.72–8.78] | 1,729 | 975 | 15,608 | 252 | ≤ 7.2·10⁻⁹ |
| 2,202 | robust clip+screen, adaptive | 3 | 23.6 [23.5–23.7] | 19.5 [19.4–19.5] | 3,984 | 1,631 | 36,056 | 3,836 | bit-exact 3/3 |
| 10,000 | sum-only | 3 | 52.9 [52.3–53.4] | 26.5 [26.0–26.9] | 5,539 | 985 | 51,448 | 252 | ≤ 5.6·10⁻⁹ |
| 10,000 | robust clip+screen, adaptive | 3 | 69.5 [69.0–70.0] | 65.1 [64.7–65.5] | 13,740 | 1,690 | 137,982 | 3,836 | bit-exact 3/3 |
| 50,000 | sum-only | 1 | 152.7 | 123.9 | 26,730 | 1,057 | 251,128 | 252 | 4.8·10⁻⁹ |
| 50,000 | robust clip+screen, adaptive | 1 | 301.7 | 295.3 | 63,560 | 2,043 | 657,726 | 3,836 | bit-exact |
| 100,000 | sum-only | 1 | 277.0 | 249.7 | 53,320 | 1,212 | 502,008 | 252 | 4.9·10⁻⁹ |
| 100,000 | robust clip+screen, adaptive | 1 | 591.8 | 586.2 | 125,800 | 2,422 | 1,307,406 | 3,836 | bit-exact |
| 250,000 | sum-only | 1 | **failed** | – | – | 1,414 (before stop) | 1,254,648 | 252 | – |

The 250,000-parameter round was **stopped by the party service's round timeout
(600 s, the default of `FL_MPSPDZ_ROUND_TIMEOUT`)**. The service log reads
`SPDZ2k round … exceeded its timeout`, and the clients then failed with
`Error while receiving`. At that point client input had been running for
448.6 s. The benchmark's own 1,800 s cap was not reached. This timeout is a
deliberate bound on how long the parties keep a round open, not a crash.

## 3. Defence variants (3 parties, K = 4)

| d | Variant | n | Total (s) | Protocol (s) | Data (MB) | Accept bits | Triples | Random bits |
|---:|---|---:|---|---|---:|---|---:|---:|
| 2,202 | clip, static τ | 2 | 23.1 [23.1–23.1] | 19.5 [19.4–19.5] | 3,994 | 1,1,1,1 (outlier clipped) | 34,612 | 3,068 |
| 2,202 | clip+screen, adaptive | 3 | 23.6 [23.5–23.7] | 19.5 [19.4–19.5] | 3,984 | 1,1,1,0 | 36,056 | 3,836 |
| 2,202 | screen only, adaptive | 2 | 17.5 [17.3–17.7] | 13.4 [13.3–13.5] | 2,581 | 1,1,1,0 | 22,892 | 1,532 |
| 10,000 | clip, static τ | 2 | 72.1 [71.9–72.3] | 68.2 [68.0–68.3] | 14,570 | 1,1,1,1 (outlier clipped) | 136,538 | 3,068 |
| 10,000 | clip+screen, adaptive | 3 | 69.5 [69.0–70.0] | 65.1 [64.7–65.5] | 13,740 | 1,1,1,0 | 137,982 | 3,836 |
| 10,000 | screen only, adaptive | 2 | 53.8 [53.6–53.9] | 49.4 [49.0–49.7] | 9,988 | 1,1,1,0 | 93,626 | 1,532 |

## 4. Number of parties (d = 2,202, K = 4)

| Program | Parties | n | Total (s) | Protocol (s) | Data (MB) | Peak RSS, all parties (MiB) |
|---|---:|---:|---|---|---:|---:|
| sum-only | 2 | 2 | 22.6 [22.5–22.8] | 4.94 [4.87–5.00] | 577 | 398 |
| sum-only | 3 | 3 | 35.0 [34.5–35.4] | 8.75 [8.72–8.78] | 1,729 | 975 |
| robust clip+screen, adaptive | 2 | 2 | 13.8 [13.8–13.9] | 11.0 [11.0–11.1] | 1,330 | 621 |
| robust clip+screen, adaptive | 3 | 3 | 23.6 [23.5–23.7] | 19.5 [19.4–19.5] | 3,984 | 1,631 |

## 5. Observations

1. **Cost is linear in the model size, and the defence adds a constant number of
   comparisons.**
   * The sum-only circuit uses exactly 5 triples per padded coordinate (one per
     client input value, one for the output) plus 248.
   * The robust circuit uses about 13 triples per coordinate with clipping and
     about 9 with screening alone. The slope between 50,000 and 100,000 parameters
     is 12.99.
   * The comparison part is independent of d: 1,532, 3,068 or 3,836 random bits
     depending on the variant, plus a few thousand triples.

   This confirms the design rule in `docs/secure_robust_aggregation.md`: no
   per-coordinate secure comparison and a constant number of comparisons per
   client.
2. **Preprocessing dominates.** Throughput was 1,900–2,230 triples per protocol
   second, at 96–108 kB of party traffic per triple. Time and traffic therefore
   follow the triple count. From 50,000 parameters upwards:
   * a robust round costs about 5.9 ms and 1.26 MB per parameter;
   * a sum-only round costs about 2.5 ms and 0.53 MB per parameter.
3. **Robust versus sum-only.**
   * Protocol time: 2.2× at 2,202 parameters, 2.3× at 100,000.
   * Total time at small sizes: the robust round is *shorter* (23.6 s vs 35.0 s at
     2,202) because the pre-existing sum-only program takes 8.5 s to compile
     against 1.3 s. This matches the per-round times in the federated evaluation.
   * Total time at 100,000 parameters: 2.1× (592 s vs 277 s).
4. **Defence variants.**
   * The adaptive median threshold costs only comparisons. Its time is the same
     as static clipping, and it is slightly lower at 10,000 parameters because
     the rejected client is not multiplied: `@if_` runs on the revealed accept bit.
   * Screening without clipping avoids the secret scalar–vector products. It
     needs 25–30 % less time and traffic, but it does not bound accepted updates
     below the screening bound.
5. **Two parties versus three.** Two parties are 1.77× faster in protocol time
   and send 3× less data, consistent with pairwise preprocessing (traffic grows
   with n(n−1)). The security model is unchanged: dishonest majority, security
   with abort, at least one honest party. However, there are fewer independent
   trust domains.
6. **Correctness.** There were 35 attempts: 34 completed and 1 failed (the
   250,000-parameter round). All 21 robust rounds were bit-exact against the
   exact integer reference (threshold, accept bits and every aggregate
   coordinate), and every output check passed. The 13 completed sum-only rounds
   deviate from float64 FedAvg by at most 1.05·10⁻⁸ (fixed-point quantisation at
   10⁶).
7. **Practical boundary on this host.** Under the default 600 s round timeout:
   * one robust round completes up to about 100,000 parameters (591.8 s, close
     to the limit);
   * sum-only rounds complete at 100,000 parameters (277 s) but not at 250,000.

   Peak party memory (all three parties) grew by about 8 KiB per parameter for
   the robust program between 10,000 and 100,000 parameters, and by about 2.5 KiB
   for sum-only.
8. **Client count was not varied** in these benchmarks; K = 4 matches the
   federated evaluation. By construction, the vector part grows linearly in K
   (inputs, norms and clipping per client) and the median sort uses K(K−1)/2
   comparisons, independent of d. The 8-client validation scenario
   (`experiments/mpc_validation/`, d = 300) is a single functional data point,
   not a benchmark.

## 6. Extrapolation (estimated, not measured)

Assume the linear trends of section 2 continue beyond 100,000 parameters, with
K = 4 and 3 parties on this host. A single round for the 2.12 M-parameter CIFAR
CNN would then need roughly:

| Program | Time per round | Loopback traffic | Peak party memory, all three parties |
|---|---|---|---|
| Robust | ≈ 3.4 h | ≈ 2.7 TB | ≈ 18 GiB (more than the host has) |
| Sum-only | ≈ 1.5 h | ≈ 1.1 TB | about 6 GiB |

Either program would also need the round timeout raised. These are estimates,
not evidence of feasibility; for this reason the CIFAR model was not trained
through SPDZ2k in this work. Real deployments would also add WAN latency and
bandwidth limits, which loopback does not show.
