# Final experimental results

## Reproducibility context

Direct runs used MP-SPDZ v0.4.3, three local parties, three deterministic synthetic clients, counts [1,2,3], ring `2^64`, `-M` memory-order preservation, 1,024-element input chunks, fixed-point scale 100,000, and a 300 s watchdog / 6 GiB RSS cap per process. Output correctness was checked against an independent Python weighted-average vector; max absolute decoded error was 0 for completed direct runs. The checked-in Flower configs can request a different party count (for example `configs/smpc.yaml` requests four); the rows below explicitly used three.

| Parameters | Direct MPC status | Total incl. cleanup | Client submit time (sum) | Offline preprocessing | Online computation | Output receive | Communication | Peak party RSS | Correctness / reason |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 8 | PASS (`-M` on) | 26.077 s | Not separately captured | ~2.5 s | ~1.6 s | Not separately captured | 487.03 MB party-log total | 302?306 MiB | max error 0; count [1,2,3] validated |
| 8 | PASS (`-M` off A/B) | 19.661 s | Not separately captured | ~2.5 s | ~1.6 s | Not separately captured | 487.03 MB party-log total | 303?307 MiB | same exact result; warning present |
| 1,000 | PASS | 27.605 s | 2.064 s | 2.43?2.51 s | 1.64?1.71 s | 0.678 s | 487.03 MB party-log total | 302?307 MiB | max error 0; count validated |
| 10,000 (initial) | FAIL at output read | 54.138 s | Submission completed; separate phase value unavailable | Not separately captured | Not separately captured | Failed: `unexpected data length` | 4.551 GB host loopback counter; protocol total unavailable | 325?330 MiB | No accepted aggregate; output framing mismatch |
| 10,000 (corrected) | PASS | 55.546 s | 15.078 s | 20.68?20.79 s | 2.83?2.94 s | 7.637 s | 4,510.11 MB party-log total | 325?331 MiB | max error 0; count validated |
| 50,000 | PASS | 141.997 s | 72.677 s | 100.7?100.8 s | 7.88?8.10 s | 36.641 s | 21,511.5 MB party-log total | 349?352 MiB | max error 0; count validated |
| 100,000 | PASS | 246.236 s | 142.888 s | 196.96?197.42 s | 16.95?17.41 s | 71.315 s | 42,999.4 MB party-log total | 388?391 MiB | max error 0; count validated |
| 250,000 | ABORTED at watchdog | 301.461 s | Did not complete; exact phase time unavailable | Did not complete; no phase total | No completed online phase | None | 59.291 GB host loopback counter; party-log protocol total unavailable | 384?388 MiB | All clients connected; no aggregate; watchdog reset socket; cleanup completed |
| 500,000 | NOT RUN as MPC | Not measured | Not measured | Not measured | Not measured | Not measured | Not measured | Not measured | Compiler-only production circuit compile had passed in prior phase; no runtime attempt |
| 2,122,187 | INCOMPLETE direct attempt | 300 s watchdog | Not recorded | Not recorded | Not recorded | None | Not recorded | Not recorded in preserved log | Earlier direct production attempt aborted without aggregate; it preceded the output-framing fix |

The full production circuit was separately compiled at 250k, 500k and 2,122,187 parameters (1.780/1.775/1.751 s, ~62.2 MiB compiler RSS, 1,003,706/2,003,130/8,491,194 triples, 29 VM rounds). Compilation is not runtime validation.

## Tiny Flower result

The chunked same-host Flower/SPDZ2k integration completed one synthetic 8-parameter round with three clients and three parties: 16.32 s total, 0.807365 s strategy aggregation, 73,728-byte metric, zero client failures. Source: `RAW_EXPERIMENT_RESULTS/flower_chunked_tiny_integration.log`. An earlier distinct tiny run recorded 0.160333 s aggregation and 648 input bytes in `same_host_tiny_spdz2k.log`; these are separate runs/configurations and must not be combined. No full-model Flower result exists.

## Interpretation

Party logs identify offline preprocessing as the main measured bottleneck: at 100k, approximately 197 s offline versus 17 s online. The client submit metric and output-receive wall time are separate harness API phases; party offline work overlaps input submission, so phase numbers must not be added as though they were sequential independent costs. Output receive wall time includes waiting/transfer and is not pure online compute. MP-SPDZ global protocol traffic is taken from party logs; the 250k value is only whole-host loopback bytes because the protocol did not finish and emit a global total.

The observed 100k pass uses 246 s of the 300 s cap. Therefore 100k is the largest successful point measured here, specific to this host/configuration; it is not a protocol-wide limit. No interpolation is used.
