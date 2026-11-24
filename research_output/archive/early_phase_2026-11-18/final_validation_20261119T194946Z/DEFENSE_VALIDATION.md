# Defense validation

## SPDZ2k secure aggregation

The pinned v0.4.3 documentation classifies SPDZ2k under **malicious, dishonest-majority** security. Its malicious model says deviation is detected; the runtime documentation gives the SPDZ2k statistical parameter default as 64, corresponding to an approximate cheating probability of 2^-58. The party invocation did not explicitly pin `-SP`, and `CONFIG.mine` is empty, so the exact effective binary/build settings were not independently attested. MP-SPDZ also cautions that the software has not received the security review expected for critical production code. The official v0.4.3 [protocol matrix](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html), [runtime options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html), and [security fixes](https://mp-spdz.readthedocs.io/en/v0.4.3/security-fixes.html) are relevant references. The security-fixes page discusses a historical SPDZ2k issue; this audit did not independently verify the exact binary's source revision or patch status.

**Demonstrated:** MP-SPDZ v0.4.3 three-party same-host executions completed on loopback. Historical raw vector runs passed at 8, 1k, 10k after a failed first 10k attempt, 50k, and 100k parameters. A fresh tiny Flower integration completed two rounds with three parties, two selected clients per round, MP-SPDZ client I/O, and secure aggregation. Invalid simulated counts, truncated output, padding corruption, ring overflow, plaintext Flower parameters, party startup failure, and missing selected clients have unit/smoke-path coverage.

**Not demonstrated:** independent cross-host parties, full-model secure aggregation, adversarial party behavior, numerical error versus plaintext over a broad randomized range, or production deployment. Successful execution does not prove protocol security beyond MP-SPDZ assumptions. The local test uses a tiny linear model and same-host parties.

## Moving Target Defense

Secret-derived schedule, minimum secret length, deterministic reproduction, and changed cohorts have focused tests. The fresh two-round pipeline selected different client sets while using a generated deployment secret. MTD rotates participation; it does not identify honest clients and did not stop malicious clients from being selected.

## Authentication and replay protection

Focused HTTP control-service tests accept a valid HMAC and reject invalid signatures, stale timestamps, duplicate/replayed requests, and reused round IDs. Replay journal persistence across service restart and round/cohort/sample-count identity binding are tested. The fresh local run completed with generated control credentials. Concurrency race resistance and remote TLS deployment were not independently stress-tested.

## Robust screening

Synthetic unit tests and the new vector microbenchmark show the plaintext detector flags selected sign-flip-like and excessive-norm vectors; in the crafted five-client case it flagged both malicious vectors and restored the constructed benign aggregate. It also rejects non-finite or duplicate-ID inputs. Its screening behavior was not evaluated on real training attacks. The Flower implementation rejects enabling this detector with SMPC because the current MPC circuit reveals only the aggregate and cannot score individual contributions.

## Combined defense

Fresh combined run: MTD + SPDZ2k + local authenticated party control + selected sign-flip client, 2 rounds. Both rounds completed and returned model updates. This is evidence of integrated functionality for a tiny same-host case. It also confirms that SMPC does not prevent poisoned inputs: selected malicious contributions were accepted. No live malformed-client or dropout injection was combined with this run.
