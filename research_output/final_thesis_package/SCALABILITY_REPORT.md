# SPDZ2k scalability and distributed validation

Date: 2026-11-18. Isolated branch research/spdz2k-thesis. Original main untouched; no commit/push.

## Decision
**B ? core MPC works, full-model execution needs optimization.** The exact production circuit compiles at full model shape under the stated caps, but one guarded direct three-party full-shape run failed to complete within 300 seconds. The 3-client/3-party Flower integration passed only with an 8-parameter synthetic model.

## Production-source compile evidence
The exact checked-in circuit source (SHA-256 1e26719b74fb35cb8c0aff5a2a12a23e21ad1d760a08070a91a8209e2e6ef333) was compiled by MP-SPDZ v0.4.3 with -R 64. Every run completed below 2s and 63MiB, within 6GiB/120s limits.

| Parameters | Compile | Peak RSS | Triples | Multiplications | Opens | VM rounds |
|---:|---:|---:|---:|---:|---:|---:|
| 250,000 | 1.780s | 62.2MiB | 1,003,706 | 251,066 | 250,886 | 29 |
| 500,000 | 1.775s | 62.2MiB | 2,003,130 | 500,922 | 500,742 | 29 |
| 2,122,187 | 1.751s | 62.2MiB | 8,491,194 | 2,122,938 | 2,122,758 | 29 |

The compiler reports 189 integer bits for these programs. Compile schedule rounds are not online latency.

For comparison, whole-vector compilation reached 68.56s/1,368MiB at 50k and timed out at 100k; vectorized whole-array reveal timed out at 250k after 120s/3,938MiB. Chunked scratch and exact production source avoid this compiler growth. Historical records are retained in SCALING_BENCHMARKS.csv and RAW_EXPERIMENT_RESULTS.

## Full-shape protocol attempt
The real production circuit and client helper processed actual CIFAR10CNN-shaped tensors with three local SPDZ2k parties and sample counts [1,2,3]. The guarded run stopped at 300s and cleaned up. No final aggregate was returned, so full-size correctness, preprocessing/online split, communication, and Flower integration at this shape remain unverified. Party processes used roughly 0.8GiB RSS each before stop; host memory and disk stayed within guard thresholds. See FULL_SHAPE_MPC_INTEGRATION.log.

For 2,122,187 float parameters plus count, padded input length is 2,122,752. With three clients, three parties, and 8-byte ring values, calculated raw client-to-party payload is 152,838,144 bytes per round before TLS/MPC overhead; padded aggregate result is 17,022,016 bytes. These are payload calculations, not observed network measurements.

## Tiny integration and suite
The prior actual Flower path passed with 3 clients, 3 local parties, an 8-parameter model and one round: 16.32s total, 0.807s aggregation, 73,728-byte metric, zero fit failures. Full suite: 70 passed, two dependency deprecation warnings. This does not prove full-model Flower operation.

MP-SPDZ emitted ?Order of memory instructions not preserved, errors possible? in compiler logs. Investigate before relying on the full-shape circuit. Only one host was available; cross-host remains unvalidated.
