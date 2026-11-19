# SPDZ2k Threat Model

## Protected assets

- Each client's weighted model update before aggregation.
- MP-SPDZ party private keys, client private keys, and coordinator control
  tokens.
- Correct execution of the weighted-sum circuit, including integrity checks
  performed by SPDZ2k.

## Roles and trust boundaries

- **Clients** hold local training data and submit model tensors multiplied by
  their server-verified example counts. Client authentication proves
  possession of a provisioned MP-SPDZ client key; it does not prove that the
  client trained honestly.
- **Aggregation parties** jointly run the pinned MP-SPDZ v0.4.3 SPDZ2k
  protocol. The dishonest-majority security assumption permits up to `n - 1`
  corrupt parties, provided at least one party is honest and the protocol
  completes.
- **Flower coordinator/output client** selects the cohort, distributes the
  global model, checks Flower proxy identities and sample counts, and receives
  the final aggregate as the designated output client.
- **Network and deployment operators** provision credentials, configure
  party/client reachability, and provide TLS for control endpoints. The
  included party service implements authenticated control requests but does
  not terminate TLS.

## In-scope adversaries and guarantees

SPDZ2k protects the private inputs and correctness of the secure computation
against malicious aggregation parties under the protocol's assumptions. If a
party deviates from the protocol or a MAC check fails, the round aborts rather
than returning a success-shaped fallback. The implementation uses authenticated
MP-SPDZ client I/O and reveals the weighted sum and total sample count only to
the configured output client.

The party control service authenticates requests with per-party HMAC keys,
rejects stale/replayed control requests, journals consumed request IDs, and
rejects reuse of a round ID. Remote control URLs must use HTTPS. The local
demo's loopback HTTP allowance is for local testing only.

The Flower strategy rejects plaintext client parameters in SMPC mode, binds
each result to its registered Flower proxy, checks that the full selected
cohort completed, and verifies reported example counts against the
server-known partitions. Any failed or missing selected client aborts the
round. Robust per-client screening is rejected in secure mode because it is
not computed within the MPC circuit.

## Explicit assumptions

- At least one of the configured aggregation parties is honest.
- Client and party keys are unique, confidential, and provisioned only to the
  intended runtime.
- The designated output client and its host are trusted with the aggregate.
- The coordinator follows the protocol sufficiently to avoid deliberately
  leaking information through cohort differencing or adversarial model
  selection.
- Deployed control endpoints, MP-SPDZ party links, and client links use
  appropriately authenticated and confidential channels.
- Party and coordinator clocks remain within the control service's five-minute
  anti-replay timestamp window.

## Out of scope and limitations

- **Availability and dropout recovery:** every selected client and every
  configured party must complete. Dropout, timeout, or protocol failure aborts
  the round; there is no threshold reconstruction or recovery.
- **All-party collusion or endpoint compromise:** collusion of all parties,
  theft of client/party keys, or compromise of the output client can expose
  private inputs or aggregates.
- **Malicious clients:** the circuit does not prove that updates came from
  honest training, enforce model norms, or provide range proofs. Poisoning
  remains possible.
- **Coordinator inference:** the coordinator sees identities, participation,
  the current model, and the final aggregate. Minimum cohort size is not
  differential privacy and does not prevent inference from repeated or
  differenced cohorts.
- **Host isolation:** the local demo uses separate processes on one machine.
  It does not protect against a shared host, kernel, root, or coordinator
  compromise.
- **Cross-host validation:** the MP-SPDZ circuit has passed a separate active
  three-party secure-sum probe, but the integrated Flower control/client path
  has not been validated across independently administered hosts.
- **Other privacy claims:** differential privacy, membership/property
  inference resistance, gradient inversion resistance, and backdoor
  attack-success-rate claims are not implemented or evaluated.

## Failure behavior

Compilation errors, mismatched bytecode, unavailable parties, client omissions,
input/output count mismatches, control authentication errors, process failures,
and secure computation/MAC failures must prevent a new global model from
being accepted. The coordinator attempts to stop all parties and clean
round-specific artifacts; cleanup errors are surfaced and do not activate a
plaintext or additive-sharing fallback.
