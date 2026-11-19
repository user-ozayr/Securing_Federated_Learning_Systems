# SPDZ2k implementation and assumptions

The project pins MP-SPDZ v0.4.3, uses `spdz2k-party.x`, arithmetic modulo 2^64, fixed-point scale 1,000,000 by default, with three parties in the direct profiling and tiny Flower smoke tests. The checked-in `configs/smpc.yaml` requests four aggregation parties; use the configuration?s actual value when reproducing a run. Client parameters are encoded, multiplied by the server-validated local sample count, and privately input to the MPC. The circuit sums these values. The private count in each client vector is compared with the corresponding public, server-known partition size; only the equality/mismatch bit is opened to the parties. A mismatch aborts.

The aggregate weighted sum and total count are opened only to the designated output client. That client checks the total against server-known expected counts before decoding. Flower receives no individual plaintext parameter arrays in secure mode. The output is the weighted average of client model states, matching FedAvg.

MP-SPDZ v0.4.3 classifies SPDZ2k as malicious security with dishonest majority, over a power-of-two ring. The protocol model provides security with abort and does not promise continued availability during malicious disruption. In a three-party run, protocol-level privacy/integrity can tolerate up to two corrupt parties only under the protocol's setup and cryptographic assumptions, with at least one party retaining the honest contribution needed for privacy; colluding parties can still force abort. This is not a claim that the deployed service or same-host experiment has independently isolated parties. Production claims require independent hosts, authenticated/encrypted network configuration, protected preprocessing/setup material, and a deployment-specific trust review.

The party service launches `spdz2k-party.x` with `-e`, which requests MP-SPDZ SSL-encrypted party connections; the local demo creates SSL material with MP-SPDZ `setup-ssl.sh`. This differs from MP-SPDZ's default for dishonest-majority protocols, which is unencrypted. The experiment exercised this setting on loopback only. Cross-host certificate distribution, identity validation, renewal, firewalling, and independent party isolation have not been validated; do not infer production network security from the same-host run.

Fixed-point encoding, ring bounds, and output decoding are implementation checks, not a proof against all malicious inputs. MP-SPDZ itself notes that the software has not undergone the security review expected for critical production code. Sources: [MP-SPDZ v0.4.3 protocol matrix](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html), [runtime ring/security/network options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html).

## Robust aggregation program (added 2026-11-20)

`programs/spdz2k_robust_aggregate.mpc` runs on the same party service, binary
(`spdz2k-party.x`), ring (`-R 64`, SPDZ2k security parameter s = 64) and client
I/O protocol as the weighted-sum program. Differences:

* **Input encoding:** clients send `[n, round((w_local − w_global)·2^f), 0-padding]`
  (default `f = 14`, chunk size 256), not `n·w`. The count binding is unchanged.
* **Computation:** per-client squared norms (dot products), optional secure
  lower-median threshold, screening (revealed accept bit) and/or clipping with
  secret coefficients (binary search, no `sfix`, no truncation). All
  comparisons are MP-SPDZ `sint` comparisons, i.e. the sign of the 64-bit ring
  difference; parameters are validated so that honest operands stay below 2⁶².
* **Output:** `[T, clipped count, accept bits, clip flags (optional), Σ a·C·w·x]`
  to the designated output client only.
* **Program identity:** the party service validates the payload
  (`weights`, `robust_spec`, `chunk_size`), prepends the validated arguments as a
  `ROUND_ARGUMENTS` literal to the packaged source, compiles without arguments
  (short bytecode name) and returns the bytecode SHA-256; parties must agree.
* **Measurements:** every completed round reports MP-SPDZ's own "Time", "Data
  sent" and "Global data sent" lines through the authenticated `status` call.
* **Cleanup:** all bytecode tapes of a round (`<name>-*.bc`) are removed; the
  previous implementation removed only `-0.bc` and left auxiliary tapes behind.

Correctness evidence: 13 real three-party scenarios match the exact integer
reference bit for bit (`research_output/completion/experiments/mpc_validation`),
and every instrumented FL run re-checks the applied update against the reference
(maximum absolute difference at float32 precision, ≈1.2·10⁻⁷).
