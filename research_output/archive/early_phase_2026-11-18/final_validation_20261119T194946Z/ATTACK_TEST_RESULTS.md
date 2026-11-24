# Attack testing results

## Fresh integrated adversarial run

A modified copy of the repository's tiny driver was run from the validation folder. It used 3 Flower clients, 3 local MP-SPDZ parties, 2 rounds, 2 selected clients per round, a one-run random `FL_MTD_SECRET`, and configured sign-flip poisoning (`compromised_fraction=0.34`, `strength=1.0`). The MTD schedule selected `[0, 1]` and `[0, 2]`; Flower reported one selected malicious client in each round. Both rounds completed through SPDZ2k. Reported central accuracy was 0.75 before and after both rounds. This tiny run has no clean baseline, no backdoor target, and no statistical attack-success measure. It establishes that selected malicious contributions can be included in secure aggregation, not that the attack is effective or mitigated.

Raw log: `INTEGRATED_TINY_MTD_ATTACK.log`. CSVs and the exact modified driver are in this folder's `integrated_tiny*` subfolders/files.

## Synthetic parameter-vector microbenchmark

`ATTACK_MICROBENCHMARK.py` runs seeded five-client vectors and records all results in `ATTACK_MICROBENCHMARK.csv`/`.json`. With two sign-flipping clients, the sample-weighted aggregate was `[0.2, 0.1]` against a benign reference `[1.0, 0.5]`, L2 deviation `0.8944`, repeated in rounds 1 and 2. With two random-noise clients, aggregate L2 deviations were `0.0751` and `0.1848` across the two rounds. Label-flip mapping transformed `[0,1,2,9]` to `[1,2,3,0]`. A separate plaintext robust-detector vector check flagged clients `[3,4]` and returned `[1,2]`, matching the constructed benign vector. These are synthetic vector effects; they do not measure trained-model accuracy, backdoor success, or secure screening.

## Existing unit-level attack evidence

- Label-flip and sign-flip transforms are tested in `tests/test_attacks.py` and `tests/test_attack_integration.py`; these tests validate transformation behavior, not global model accuracy or attack success rate.
- `ByzantineAttacker` implements sign flip, label flip, and seeded random noise. Random replacement and targeted backdoor attacks are unsupported by the implementation.
- Robust detector tests exercise sign-flip-like vectors, excessive norm, NaN/infinity rejection, duplicate client-ID rejection, and history inconsistency. The detector is a plaintext aggregation path and cannot currently be enabled with the sum-only SMPC circuit.
- `tests/test_mp_spdz.py` checks ring overflow, invalid count, truncated output, and nonzero padding rejection using mocked client I/O. These do not inject malformed messages into a live multi-party execution.

## Untested efficacy claims

No controlled CIFAR/model study measured attack success rate, clean accuracy loss, parameter deviation on a trained model, repeated-round model effect, or coordinated-client model impact. The vector microbenchmark measures aggregate deviation only on constructed inputs. Label-flip, random-noise, large-magnitude in-range update, random replacement, targeted backdoor, and dropout effectiveness were not independently evaluated. Do not convert these into prevention claims.
