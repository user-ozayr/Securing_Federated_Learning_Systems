# Runtime profile: production SPDZ2k weighted sum

## Setup and scope

Runs used the isolated `research/spdz2k-thesis` checkout, three local MP-SPDZ parties and three deterministic synthetic clients, production weighted-sum circuit, `-R 64`, chunk size 1,024, counts [1,2,3], and a 100,000 fixed-point scale. Each benchmark had a 300 s watchdog and 6 GiB per-process RSS guard. Values are direct production client-I/O runs, not Flower runs. `PROGRESSIVE_MPC_EXECUTION.csv` preserves the harness records; `RESOURCE_USAGE.csv` contains the sampled per-party RSS/CPU/disk data. Per-process disk counters were zero in all samples; the large traffic is loopback network traffic, not measured disk I/O.

## Phase breakdown

| Parameters | Client submit | Output receive | Party offline/preprocessing | Party online | Total incl. cleanup | Host loopback | Peak party RSS | Result |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 8 | n/a | n/a | ~2.5 s | ~1.6 s | 26.077 s (`-M`); 19.661 s (`-M` off) | 0.492 GB | 302?306 MiB | PASS, A/B |
| 1,000 | n/a | n/a | 2.43?2.51 s | 1.64?1.71 s | 27.605 s | 0.492 GB | 302?307 MiB | PASS |
| 10,000 | 15.078 s | 7.637 s | 20.68?20.79 s | 2.83?2.94 s | 55.546 s | 4.551 GB | 325?331 MiB | PASS after output framing fix |
| 50,000 | 72.677 s | 36.641 s | 100.7?100.8 s | 7.88?8.10 s | 141.997 s | 349?352 MiB | 366?370 MiB | PASS |
| 100,000 | 142.888 s | 71.315 s | 196.96?197.42 s | 16.95?17.41 s | 246.236 s | 407?410 MiB | 388?391 MiB | PASS |
| 250,000 | did not finish | did not finish | not completed | not completed | 301.461 s watchdog | 59.291 GB | 384?388 MiB | ABORTED after 300 s |

Party logs report 401,594 triples and 29 VM rounds at 100k; the protocol reports 42,999.4 MB global data sent. At 50k the logs report 200,890 triples, 29 rounds and 21,511.5 MB global data sent. At 10k: 41,146 triples, 29 rounds, 4,510.11 MB. Traffic is MP-SPDZ protocol communication, whereas loopback counters are whole-host sampled totals; these measurements are related but not identical.

## Bottleneck conclusion

At 100k, MP-SPDZ party logs attribute about 197 s to offline/preprocessing and about 17 s to online computation. Party-to-party protocol traffic is about 43.0 GB. Client input communication was about 24.1 MB per party and 13?16 s. Thus preprocessing and its communication dominate the completed large runs. The 250k run connected all clients, spent 17.85 s in party setup, then remained incomplete until the watchdog killed the runner; it did not produce an aggregate. The final party log shows socket reset after watchdog termination. RSS remained far below the 6 GiB cap, and no process disk traffic was observed.

The 100k pass is close to the 300 s cap and does not provide enough headroom to attempt 500k or full shape safely under this benchmark policy. No exact full-shape runtime is extrapolated from these measurements.

## Limits

The harness measures combined local setup/API/cleanup wall time and samples process resources. Party log timings separate client communication, offline and online phases, but do not separately expose MAC verification, final aggregate delivery, and party completion as independently timed milestones. Output receive wall time includes waiting and transfer; it should not be read as pure protocol compute. CPU tick totals are estimates from samples. Same-host loopback measurements do not establish cross-host performance.
