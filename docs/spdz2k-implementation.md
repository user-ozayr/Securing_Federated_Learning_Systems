# SPDZ2k implementation and assumptions

The project pins MP-SPDZ v0.4.3 and runs `spdz2k-party.x` over the ring modulo 2^64. The default fixed-point scale is 1,000,000. Direct profiling and the small Flower smoke tests used three parties. The checked-in `configs/smpc.yaml` requests four aggregation parties, so a reproduction should use the value specified by its configuration.

For each client, the server validates the local sample count, multiplies the encoded model parameters by that count, and privately inputs the result to the MPC. The circuit sums the weighted parameters. It also compares the private count in each client vector with the corresponding public count known to the server. Only the equality or mismatch bit is opened to the parties. A mismatch aborts the round.

The weighted sum and total count are opened only to the designated output client. Before decoding the result, that client checks the total against the expected count known to the server. In secure mode, Flower does not receive individual plaintext parameter arrays. The output is the weighted average of the client model states, as in FedAvg.

MP-SPDZ v0.4.3 classifies SPDZ2k as maliciously secure with dishonest majority, using a power-of-two ring. Its protocol model provides security with abort; it does not guarantee availability when a malicious party disrupts the run. In a three-party run, protocol-level privacy and integrity can tolerate up to two corrupt parties only under the protocol's setup and cryptographic assumptions, with at least one party retaining the honest contribution required for privacy. Colluding parties can still force an abort. These properties do not mean that the deployed service or the same-host experiment uses independently isolated parties. Production claims require separate hosts, authenticated and encrypted network configuration, protected preprocessing and setup material, and a deployment-specific trust review.

The party service starts `spdz2k-party.x` with `-e`, which requests SSL-encrypted party connections. The local demo creates SSL material with MP-SPDZ `setup-ssl.sh`. MP-SPDZ otherwise defaults to unencrypted connections for dishonest-majority protocols. The experiment used the encrypted setting on loopback only. Cross-host certificate distribution, identity validation, renewal, firewalling, and independent party isolation remain unvalidated. The same-host run therefore provides no evidence of production network security.

Fixed-point encoding, ring bounds, and output decoding are implementation checks. They do not prove security against every malicious input. MP-SPDZ also notes that the software has not received the security review expected of critical production code. Sources: [MP-SPDZ v0.4.3 protocol matrix](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html) and [runtime ring, security, and network options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html).

## Robust aggregation program (added 2026-11-20)

`programs/spdz2k_robust_aggregate.mpc` uses the same party service, binary (`spdz2k-party.x`), ring (`-R 64`, SPDZ2k security parameter s = 64), and client I/O protocol as the weighted-sum program. Its input and computation differ:

* **Input encoding:** Clients send `[n, round((w_local - w_global)·2^f), 0-padding]` (default `f = 14`, chunk size 256), rather than `n·w`. Count binding is unchanged.
* **Computation:** The circuit computes per-client squared norms using dot products, then optionally applies a secure lower-median threshold, screening (with the accept bit revealed), and/or clipping with secret coefficients. Clipping uses binary search without `sfix` or truncation. Comparisons use MP-SPDZ `sint`, meaning the sign of the 64-bit ring difference. Honest operands are validated to remain below 2^62.
* **Output:** The designated output client alone receives `[T, clipped count, accept bits, clip flags (optional), Σ a·C·w·x]`.
* **Program identity:** The party service validates the payload (`weights`, `robust_spec`, `chunk_size`), prepends the validated arguments as a `ROUND_ARGUMENTS` literal to the packaged source, compiles without arguments to produce a short bytecode name, and returns the bytecode SHA-256. Parties must agree on that hash.
* **Measurements:** Each completed round reports MP-SPDZ's own “Time”, “Data sent”, and “Global data sent” lines through the authenticated `status` call.
* **Cleanup:** The service removes every bytecode tape for the round (`<name>-*.bc`). The previous implementation removed only `-0.bc`, leaving auxiliary tapes behind.

Correctness evidence:

* Thirteen real three-party scenarios match the exact integer reference bit for bit (`research_output/completion/experiments/mpc_validation`). The scenarios were repeated from a fresh clone.
* The same bit-for-bit match holds for 21 benchmark rounds with up to 100,000 parameters.
* Every instrumented federated-learning run checks the applied update against the reference. Across 70 SPDZ2k robust runs (700 rounds), the maximum absolute difference was 2.4·10⁻⁷ and the median per-run difference was 1.2·10⁻⁷, at float32 model resolution. The maximum relative difference was 2.0·10⁻⁷.
* Training trajectories match the plaintext execution of the same algorithm (`research_output/completion/FINAL_VALIDATION_REPORT.md`, sections 3–4).
