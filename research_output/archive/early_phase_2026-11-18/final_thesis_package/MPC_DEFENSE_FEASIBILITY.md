# MPC defense feasibility: per-tensor norm clipping

## Status
A standalone SPDZ2k prototype works for two-coordinate vectors. It is not integrated into production Flower aggregation and is not full-model evidence.

## Arithmetic reviewed
The prototype sets sfix to 16 fractional bits and 31 total bits, and enables round_nearest. MP-SPDZ documents the default sfix signed range as about 2^14 (roughly 16,000) with 2^-16 resolution. It warns that fixed-point multiplication/division use probabilistic truncation by default; nearest rounding avoids that mode at additional cost.

The circuit computes a squared norm, substitutes 1 when the norm squared is exactly zero, calls InvertSqrt, and chooses scale 1 when norm squared <=1. This avoids zero division in the implemented branch. InvertSqrt is documented in MP-SPDZ v0.4.3 as a reciprocal-square-root approximation citing Lu et al.; code uses bit decomposition and an approximation polynomial. The local function contract does not specify a malicious-input domain/range guarantee. A wrapped or negative norm caused by input/intermediate overflow is not safely handled. No secure input magnitude or accumulated norm bound is enforced.

The optimized circuit avoids secret division: it returns weighted clipped sums; the public total sample count is used by the output client outside MPC. The earlier sqrt/division prototype was also functionally tested only on small vectors.

## Measured scenarios
| Scenario, 2 coordinates/client | Max aggregate error vs Python | End-to-end |
|---|---:|---:|
| Large updates, two clients over norm bound | 0.001334 | 12.33s |
| All updates below bound | 0.00000382 | 12.35s |
| Within-bound sign flip | 0.000000763 | 12.28s |

The within-bound sign flip remains in the aggregate. Party logs report 4.48s protocol time including preprocessing, 163.3MB sent by party 0, and 489.2MB total three-party traffic; end-to-end includes startup.

At 250 coordinates the circuit compiled in 1.26s, 47.5MiB, 67,147 triples, 338 rounds. Linear extrapolation to 2,122,187 parameters is about 570 million triples and is not a measurement. Earlier coordinate-wise secure comparison/selection estimate is about 254.7m triples, also extrapolated. Fixed-point error/approximation and model-scale runtime/communication need characterization. Conclusion: retain as research prototype/future work, not a production defense.
