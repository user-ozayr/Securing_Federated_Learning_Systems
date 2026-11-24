# Security and Evidence Limitations

This list is deliberately explicit. Each item states what is **not** established
by the implementation or the evidence, so that no result in this directory is
read more broadly than it supports.

## A. Cryptographic and protocol scope

1. **Same-host deployment only.** All three SPDZ2k parties, the coordinator and
   all clients ran on one machine (loopback networking, one kernel, one
   administrator). The evidence shows protocol integration and correctness, not
   independence of trust domains. Cross-host deployment was not executed.
2. **Security with abort, no availability.** Any party, any selected client or a
   malformed input can stop a round (abort or rejected update). There is no
   dropout recovery. Observed in the evaluation: (a) without a defence, attacks
   that make the model diverge end in a fail-closed abort of the sum-only secure
   round once the fixed-point encoder refuses the diverged weights (5 runs);
   (b) one transient TLS-handshake reset between a client and a party aborted a
   round. That is one in about 4,100 SPDZ2k client submissions, each of which
   opens one TLS connection to every party. The run was repeated, and the failed
   attempt is archived under `experiments/failed_attempts/`.
3. **Honest-party assumption.** Confidentiality needs at least one honest party
   and confidential keys; collusion of all parties reveals the inputs.
4. **Output client trust.** The designated output client (the coordinator in this
   prototype) sees the aggregate and the declared metadata.
5. **MP-SPDZ itself** has not been independently reviewed for production use (its
   own documentation says so); this project relies on its SPDZ2k implementation
   and its published security model.

## B. In-MPC defence

6. **Norm bounds are not anomaly detection.** Updates whose magnitude is honest
   but whose direction is malicious (label flipping, sign flipping at honest
   magnitude, low-norm backdoors) are only attenuated when they exceed the bound.
7. **Colluding encoding-level attackers** can exceed the per-client bound by
   cancelling wrap-around components (demonstrated with 8 clients in
   `experiments/mpc_validation`, scenario `colluding_cancellation_k8`). The output
   check bounds the applied update only by the round threshold. Per-coordinate
   range proofs are not implemented.
8. **Median manipulation.** Inflated norms move the lower median once they make
   up more than ⌊K/2⌋ of a cohort, i.e. three or more of four participants.
   Deflated norms lower the threshold (bounded below by `min_norm`), which slows
   learning. The evaluation reached at most two attackers in a four-client
   cohort, which the defence still handled (E4, m = 5); three or more were not
   tested.
8b. **Heterogeneous honest updates.** Under non-IID data (E5, Dirichlet 0.5),
   honest updates exceeded the screening bound ρ·τ and were rejected: 2 of 29
   honest participations in one seed, none in the other. With IID data no
   honest client was ever rejected.
9. **Clipping at the median attenuates honest updates.** With `λ² = 1` about
   half of the honest participants are clipped every round by construction; the
   evaluation reports this cost (accuracy, deviation from honest FedAvg).
10. **Revealed metadata.** The threshold, the clipped count, the screening
    decisions and (evaluation setting) per-client clip flags are revealed. The
    evaluation runs enable per-client flags to measure detection; a deployment
    should disable them.
11. **Quantisation.** Clip coefficients are floor-rounded to `2^-g`; updates larger
    than `2^g·τ` are dropped; non-uniform sample weights are quantised.

## C. Moving Target Defence

12. MTD does not detect or exclude malicious clients; it only removes the
    adversary's ability to *predict* participation. The guarantee depends on the
    secrecy of `FL_MTD_SECRET`.
13. Secret-schedule runs are reproducible only with the secret (only a SHA-256
    commitment is stored).
14. Comparisons of static versus dynamic participation also differ in data
    coverage (four clients vs all clients over time).

## D. Experimental scope

15. **Small model and dataset.** Fashion-MNIST with a 2,202-parameter CNN was
    chosen so that multi-round, multi-seed SPDZ2k experiments are feasible on a
    3-core host. Results do not transfer automatically to large models; the
    2.12 M-parameter CIFAR CNN was not trained through SPDZ2k (see the benchmark
    scaling evidence for the cost boundary).
16. **Few seeds.** Three seeds per condition (two for sweeps and non-IID); the
    95 % intervals are wide and small differences are not resolvable.
17. **Short training.** Ten rounds; long-horizon effects (e.g. slow backdoor
    accumulation over hundreds of rounds) are not covered.
18. **Attack coverage.** Label flip, sign flip, scaled replacement, Gaussian noise,
    BadNets backdoor (naive and adaptive constrain-and-scale), and schedule-aware
    adversaries. Not evaluated: optimisation-based attacks (e.g. inner-product
    manipulation, "a little is enough"), edge-case/semantic backdoors, Sybil
    attacks beyond the fixed malicious count, membership and property
    inference. Gradient inversion is evaluated only for single-step (FedSGD)
    updates and a passive coordinator (E6).
18b. **Secure aggregation is not data privacy.** E6 shows that the SPDZ2k
    aggregate of a four-client cohort can still contain exact copies of
    individual training images when the model has a fully connected first layer:
    75–100 % of a client's images at B = 1, 3–28 % at B = 8. The coordinator
    loses only the attribution to a client. Larger cohorts and batches, many
    local steps, or differential privacy reduce this; none of them is enforced
    by the framework.
19. **Timing.** Wall-clock values come from a shared 3-core host; MPC party
    processes compete with each other and with Ray actors. Communication volume
    is MP-SPDZ's own count of party-to-party data (loopback), not a WAN
    measurement.
20. **Plaintext reference runs** (`reference_defence`, `reference_clip`) execute the
    same integer algorithm without cryptography; they are labelled as such and
    are used only for parameter sweeps and for the equivalence check against
    SPDZ2k runs.
21. **Static-cohort artefact in E4.** With stratified placement and static
    participation, the malicious-count sweep (1, 2, 4, 5 of 12) puts 0, 1, 1 and
    2 attackers into the fixed four-client cohort. The sweep therefore varies
    the in-cohort count only between 0 and 2.
22. **Adaptive attacker model.** The adaptive attacker knows the threshold of
    the current round, because the defence publishes it (worst case). A design
    that keeps the threshold secret was not evaluated.
23. **Scale.** Rounds longer than the parties' 600 s round timeout fail. On this
    host that limits a robust round to about 100,000 parameters (measured), and
    the 2.12 M-parameter CIFAR CNN is only extrapolated (about 3.4 h per round).

## E. Moving-target direction screen (branch `research/mtd-defence`)

Details in `research_output/mtd_defence/MTD_DEFENCE_REPORT.md`.

24. **Detection scope.** The sign-agreement screen catches direction changes
    (label flip: 88–93 % of attacker participations rejected). Norm-constrained
    backdoors are rejected in only 10–35 % of participations, and an evasive
    attacker that copies clean values into a guessed 25 % of the coordinates
    is rejected in 4–13 %.
25. **Honest majority required.** The majority-of-others vote and the median
    threshold both fail when attackers are at least half of a cohort. Random
    cohorts of 4 out of 12 with 3 attackers contain two or more attackers in
    about 24 % of rounds; MTD reduces how often a *targeting* adversary
    reaches a majority but cannot exclude it.
26. **Cost.** A secret 25 % subset costs about 6 × the norm defence per round
    inside SPDZ2k (d = 2,202, K = 4: 148 s vs 21 s protocol time, 29.5 GB vs
    4.3 GB traffic).
27. **Secret dependence.** The secret subset relies on `FL_MTD_SECRET`; with a
    known subset the evasive attacker is as successful as against a public one.
28. **Pairing.** Only P3 compares MTD conditions on identical secret cohorts;
    M1–M3 and F1 draw a fresh secret per run, so their MTD-vs-static
    differences include cohort-draw variance. An M3 conclusion based on such a
    difference was withdrawn (report §5.3).
29. **Five seeds.** P3's paired differences are consistent in direction, but
    sign tests over five seeds reach p = 0.031 (one-sided) at best, and the
    comparisons against "secret MTD, norm only" are not significant.
30. **Hidden threshold** (item 22). The pilot shows that the adaptive attacker's
    norm equals the honest-median threshold (1.00 × T), so hiding or moving
    the norm threshold alone would not separate it.

## F. Claims that must not be made from this evidence

* that SPDZ2k (or the framework) *prevents* poisoning;
* that MTD guarantees exclusion of malicious clients;
* that the direction screen detects stealthy (norm-constrained) backdoors
  reliably, or that the MTD + screen combination is significantly better
  than secret MTD alone;
* differential privacy or resistance to inference attacks;
* production readiness, cross-host security, or full-CIFAR-scale secure training.
