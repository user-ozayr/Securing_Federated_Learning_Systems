# Final security and threat-model audit

## Parties and roles

- **Flower clients** hold local data and submit one authenticated ExternalIO vector per selected client. The vector contains the sample count followed by fixed-point weighted floating-point model values, padded to 1,024-value chunks. Client authentication proves possession of a provisioned credential, not honest training or a truthful model update.
- **Three aggregation parties in the measured direct runs** execute the same MP-SPDZ v0.4.3 SPDZ2k bytecode. Some YAML files request four parties; party count is configuration-specific. The direct performance results are all three-party same-host runs.
- **Flower coordinator / designated output client** selects the cohort and model, knows server-side partition sizes, and receives the final weighted aggregate and total count. It does not receive individual plaintext parameter arrays on the secure path.
- **Control service** accepts HMAC-signed start/status/stop/cleanup requests. The local demo binds its HTTP service to loopback; configured remote control URLs are required to use HTTPS. The service does not itself terminate TLS.

## Adversary model and collusion

MP-SPDZ v0.4.3 classifies `spdz2k-party.x` as malicious security in the dishonest-majority model. The usual confidentiality interpretation requires at least one aggregation party remain honest; with three parties this is the n?1 corrupt-party dishonest-majority setting under MP-SPDZ's protocol and setup assumptions. If all parties collude, the project makes no privacy guarantee. Malicious behavior can cause abort; availability and guaranteed completion are not provided. MP-SPDZ itself cautions that the framework is not independently security-reviewed to critical-production standards. These are protocol-model claims, not a deployment audit.

The service launch command passes `-e`; the local demo provisions party SSL material with MP-SPDZ `setup-ssl.sh`. Therefore the tested same-host runtime requests encrypted MP-SPDZ party connections, despite MP-SPDZ's documented unencrypted default for dishonest-majority protocols. The loopback experiment did not validate cross-host certificate deployment, trust/identity policy, renewal, firewalls, endpoint isolation, or actual network attack resistance.

## Information visible and opened

- Each party receives the circuit, selected logical IDs, expected per-client sample counts, and public execution metadata. Client input values are sent through authenticated MP-SPDZ client I/O and are secret-shared into SPDZ2k; a party sees its protocol share, not a plaintext vector, under the protocol assumptions.
- The circuit opens the per-client count mismatch/equality result to the MPC computation so it can abort when a private input count differs from the public expected count. The expected sample counts are already known to the coordinator and configured into the circuit.
- The weighted sum and total example count are revealed only to the designated output client. The coordinator consequently learns the global aggregate, total count, cohort identities/participation, model state, and run metadata. Repeated/differenced cohorts may support inference; minimum cohort size is not differential privacy.
- No differential privacy, model-update range proof, per-client norm bound, membership-inference resistance, or poisoning resistance is provided by this sum circuit.

## Integrity, authentication, and abort behavior

- The service authenticates control requests using HMAC-SHA256 over method, route, timestamp, unique request ID and request body; it rejects stale requests, replayed IDs, and reused round IDs using persistent journals. Unit tests cover authentication/replay and journal persistence. Secret values are not included here.
- The secure Flower strategy binds proxy IDs to selected clients, checks the complete selected cohort, compares reported example counts to server-known partition counts, checks client input-submitted metrics, rejects plaintext fit parameters, and requires the exact `mp_spdz_spdz2k` backend. Configuration rejects unsupported backend and dropout-recovery settings.
- Party services compile the same program and check bytecode identity. MP-SPDZ SPDZ2k includes authenticated shares/MAC verification; the source does not disable protocol checking. A malicious MAC-failure injection was not performed, so failure handling is supported by protocol/framework and code-path review, not a dedicated negative MPC experiment.
- Startup, client omission, count mismatch, invalid output, process failure, or protocol error causes abort/cleanup; secure mode has no plaintext/additive-sharing fallback. The 250k watchdog run cleaned up and returned no aggregate. There is no dropout recovery or threshold reconstruction. A full failed-party or network partition test was not performed.

## MTD and robust detection

MTD changes client selection; it does not assign independent MPC parties or guarantee that selected clients are honest. With `FL_MTD_SECRET` of at least 32 bytes, the controller derives an HMAC-SHA256 key and creates a round-scoped schedule. Without it, the schedule is reproducible from the configured public seed and is not secret. The checked-in `configs/smpc.yaml` disables MTD and the tiny smoke records `mtd_secret_seeded=0`; secret-backed scheduling has unit tests but no measured security/robustness experiment.

The robust update detector computes per-client norms, directions and temporal scores from plaintext updates. The current sum-only SMPC strategy rejects this combination. It must not be described as a private MPC detector or as validated poisoning defense. MPC-BCD and production norm clipping are not implemented.

## Remaining attack surface and untested properties

Malicious clients can submit arbitrary vectors within the input format; the circuit does not prove honest local training, semantics, or bounds. The coordinator can influence model/cohort selection and may infer information by repeated aggregation. DoS, compromised coordinator/output client, stolen keys, all-party collusion, malicious control host, host root/kernel compromise, and side channels are not addressed by the experiment. Cross-host operation, production key lifecycle, network identity policy, malicious MAC-failure injection, party dropout injection, and independent cryptographic review remain untested.

Primary protocol references: [MP-SPDZ v0.4.3 protocol classification](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html#protocols), [runtime security and SSL options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html), [MP-SPDZ project security-review caveat](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html#preface).
