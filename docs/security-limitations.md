# Security limitations

Implemented and tested: HMAC-authenticated party control requests with
timestamps and request IDs; persistent replay rejection; round reuse
protections; TLS policy for control endpoints; client/proxy identity checks;
server-side partition-count validation; an MPC equality check binding private
count input to the public expected count; no plaintext-update fallback in
secure mode; party failure cleanup (all round tapes); bytecode hash agreement;
an in-MPC norm defence (secure clipping and/or screening with an adaptive
lower-median threshold) with a validated bit budget and a plaintext
output-norm check; secret-derived MTD schedules with explicit validation.

Protocol assumptions: MP-SPDZ v0.4.3 SPDZ2k provides malicious security in the
dishonest-majority model with abort. It does not ensure availability. Party
links are started with `-e` (encrypted) and local runs provision SSL material.

Defence limitations:

* **Within-bound attacks** remain possible: label flipping, sign flipping at
  honest magnitude and small-norm backdoors are attenuated only to the extent
  that they exceed the bound; norm bounds cannot detect directionally malicious
  updates of honest size.
  * Measured: an adaptive backdoor scaled to 0.95 × the published threshold was
    never rejected and reached ASR up to 0.35 (E2).
  * Label flipping was only partly mitigated (E1).
* **Heterogeneous honest updates** can exceed the screening bound. Under
  non-IID data (Dirichlet 0.5, E5), 2 of 29 honest participations were rejected
  in one seed; with IID data no honest client was rejected.
* **Colluding encoding-level attackers** can exceed the per-client bound by
  cancelling wrap-around components; the output check limits the applied update
  to the round bound. Per-coordinate range proofs would close this gap and are
  not implemented (≈126 triples per coordinate and client).
* **Threshold manipulation**: a majority of the cohort can move the median; at
  most ⌊K/2⌋ inflated norms leave the lower median honest. Deflated norms can
  lower the threshold (clamped at `min_norm`), slowing training.
* **Leakage** beyond the aggregate: the round threshold, the clipped count, the
  screening decisions, and – when enabled for evaluation – per-client clip flags.
* **No differential privacy**, no membership/property-inference or
  gradient-inversion protection, no dropout recovery.

Not established: full CIFAR-scale integrated execution (2.12 M parameters),
cross-host deployment, production key lifecycle, independent party isolation,
resistance to denial of service, independent cryptographic review of MP-SPDZ or
of this program. All experiments ran on one host and therefore do not test
independent trust domains.
