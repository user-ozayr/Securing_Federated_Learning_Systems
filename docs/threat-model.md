# Threat Model: SPDZ2k Aggregation, In-MPC Norm Defence and MTD

## Protected assets

- Each client's model update before aggregation (confidentiality).
- The integrity of the aggregate: each accepted client's influence is bounded
  (when the in-MPC defence is enabled).
- MP-SPDZ party private keys, client private keys, coordinator control tokens,
  and the MTD scheduling secret.
- Correct execution of the secure programs, including SPDZ2k's MAC checks.

## Roles and trust boundaries

- **Clients** hold local training data. In sum-only mode they submit model
  tensors multiplied by their server-verified example counts; in robust mode
  they submit their update `w_local − w_global` at scale `2^f`. Client
  authentication proves possession of a provisioned MP-SPDZ client key; it
  does not prove that the client trained honestly or encoded honestly.
- **Aggregation parties** jointly run the pinned MP-SPDZ v0.4.3 SPDZ2k
  protocol (dishonest majority, security with abort): up to `n − 1` corrupt
  parties are tolerated as long as one party is honest.
- **Flower coordinator / output client** selects the cohort (MTD), distributes
  the global model, checks Flower proxy identities and sample counts, receives
  the revealed outputs, performs the plaintext output-norm check and updates the
  global model.
- **Network and deployment operators** provision credentials, configure
  reachability, and terminate TLS for the control endpoints.

## Adversaries considered

| Adversary | Capability | Mitigation in this framework | Residual risk |
|---|---|---|---|
| Curious coordinator | observes everything sent to it | sees only revealed outputs (aggregate, threshold, accept/clip flags as configured) | inference from aggregates of small or differenced cohorts |
| Malicious MPC parties (≤ n−1) | deviate arbitrarily | SPDZ2k MACs → abort; bytecode hash agreement | denial of service (abort); all-party collusion breaks confidentiality |
| Malicious clients (training-level) | poisoned data or manipulated updates within the encoding | in-MPC clipping/screening bounds each accepted contribution | attacks within the bound (e.g. small-norm backdoors, label flipping) still have influence |
| Malicious clients (encoding-level, single) | arbitrary ring elements (wrap-around) | decisions on the visible contribution + plaintext output check | round rejected (availability), never a silently enlarged update |
| Colluding malicious clients (encoding-level) | inputs whose huge components cancel | output check bounds the applied update by the round bound | per-client bound can be exceeded inside that ball; needs range proofs (not implemented) |
| Predictive adversary | knows the public configuration/seed; compromises clients it expects to be selected | secret-derived HMAC schedule (`FL_MTD_SECRET`) | none beyond random guessing while the secret stays secret; a selected malicious client still submits malicious updates |
| Adaptive (defence-aware) attacker | knows thresholds; scales its update to just below them | bound limits its per-round magnitude | maximal-within-bound influence (measured in study E2) |

## Guarantees (and their conditions)

1. **Confidentiality of individual updates** against the coordinator and up
   to `n − 1` parties: standard SPDZ2k guarantee, conditional on at least one
   honest party and confidential keys. The coordinator never receives
   individual tensors in SMPC mode.
2. **Correctness or abort** of the secure computation: SPDZ2k with MAC checks.
3. **Bounded per-client influence** (robust mode): every accepted contribution
   satisfies the configured L2 bound, *or* the round's update is rejected – for
   any number of honest-format clients and at most one encoding-level malicious
   client (`docs/secure_robust_aggregation.md`, §4–5).
4. **Unpredictable participation**: with `mtd.schedule: secret`, cohort
   prediction by an adversary without the secret is no better than chance
   (measured: hit rate ≈ K/N = 0.33 for random, predictive and just-in-time
   adversaries; 1.0 for just-in-time against static/deterministic schedules).

## Explicit assumptions

- At least one aggregation party is honest.
- Client and party keys are unique, confidential, and provisioned only to the
  intended runtime; `FL_MTD_SECRET` (≥ 32 bytes) is known only to the coordinator.
- The designated output client and its host are trusted with the aggregate.
- The coordinator follows the protocol (no deliberate cohort differencing).
- Deployed control endpoints, MP-SPDZ party links and client links use
  authenticated, confidential channels; clocks are within the five-minute
  anti-replay window.

## Out of scope and limitations

- **Availability and dropout recovery:** every selected client and every party
  must complete; any failure aborts the round. Malformed inputs that trigger the
  output check cause the round's update to be skipped.
- **Encoding-level collusion:** see the table above; per-coordinate range proofs
  are not implemented (cost: one secure comparison per coordinate).
- **Within-bound poisoning:** norm bounds do not detect attacks whose updates
  look like honest updates in magnitude (label flipping, small backdoors,
  sign-flip at honest magnitude). They limit, but do not remove, such influence.
- **Inference attacks:** differential privacy, membership/property inference
  and gradient-inversion resistance are not implemented. Revealed thresholds and
  (optionally) per-client flags are additional leakage, documented in
  `docs/secure_robust_aggregation.md` §7.
- **Host isolation:** the evaluation runs all parties, clients and the
  coordinator on one host. This validates protocol integration, not isolation
  between independently administered trust domains.
- **Cross-host deployment:** not validated.

## Failure behaviour

Compilation errors, mismatched bytecode, unavailable parties, client omissions,
input/output count mismatches, control authentication errors, process failures
and MAC failures prevent a new global model from being accepted; the
coordinator stops all parties and removes round-specific artefacts (all
bytecode tapes of the round). No plaintext or additive-sharing fallback exists
in SMPC mode. A failed output-norm check keeps the previous global model and is
logged per round.
