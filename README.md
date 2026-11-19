# Securing Federated Learning with MTD and MP-SPDZ

Research prototype for horizontal federated learning, Moving Target Defence
(MTD), poisoning experiments, and secure aggregation using MP-SPDZ v0.4.3
with the SPDZ2k protocol.

## Requirements and local demonstration

Use Python 3.11, install the Flower simulation extra, and build the pinned
MP-SPDZ release on a supported Linux host:

    python -m pip install -e ".[simulation,dev]"
    pytest -q

The local MP-SPDZ demonstration requires a pre-built MP-SPDZ v0.4.3 tree. Set
`FL_MPSPDZ_HOME` to that tree and run:

    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
      python run_experiment.py \
      --config configs/benchmark_lr001/hybrid_verified.yaml --local-mp-spdz

The documented primary hybrid configuration is
`configs/benchmark_lr001/hybrid_verified.yaml`: MTD selection, SPDZ2k aggregation,
and sign-flip simulation are enabled; contribution clipping is not implemented.
It requests four aggregation parties. The command is the intended full-model
entry point, but a full CIFAR Flower round has not yet completed successfully;
see `docs/experimental_methodology.md` and the runtime reports before making
scalability claims.

This command creates temporary party and client TLS credentials, starts one
party-control service per configured MPC party, runs Flower, and shuts the
services down. CIFAR-10 is downloaded by torchvision into `./data`; metrics
are written to the configured output directory. The local demo requires Linux
and MP-SPDZ build tools.

The party processes, Flower server, and simulated clients share one host and
kernel in this demonstration. It validates protocol integration and message
flow, not isolation from a compromised host, coordinator, worker, or party.

The server uses the Flower 1.38.x simulation API (`start_simulation` and a
custom strategy); migration to Flower's ClientApp/ServerApp model is not part
of this prototype.

## Distributed deployment

Each aggregation party needs:

- The same MP-SPDZ v0.4.3 build and the packaged
  `spdz2k_weighted_sum.mpc` program.
- Its party TLS certificate and private key under `Player-Data/`.
- A party IP file listing every party as `host:port`, with the same party
  order on each host.
- A unique coordinator control token, provisioned only to that party and the
  coordinator.
- A reachable client-I/O port at `FL_MPSPDZ_CLIENT_PORT_BASE + party_id`.

Run one party service per host/container with
`python -m fl_security.smpc.mp_spdz_party_service`. Configure the service
environment with `FL_MPSPDZ_HOME`, `FL_MPSPDZ_WORK_DIR`, `FL_MPSPDZ_IP_FILE`,
`FL_MPSPDZ_PARTY_ID`, `FL_MPSPDZ_PARTY_COUNT`,
`FL_MPSPDZ_CLIENT_PORT_BASE`, and `FL_MPSPDZ_CONTROL_TOKEN`. The optional
`FL_MPSPDZ_SERVICE_HOST`, `FL_MPSPDZ_SERVICE_PORT`, and
`FL_MPSPDZ_ROUND_TIMEOUT` control its listener and timeout.

The Flower coordinator must set `FL_MPSPDZ_HOME`,
`FL_MPSPDZ_CLIENT_PORT_BASE`, `FL_MPSPDZ_CLIENT_CREDENTIALS_DIR`, and
`FL_MPSPDZ_PARTIES_JSON`. The party JSON maps each ID to a control URL, a
unique control token, and the host clients use for MP-SPDZ client I/O:

    {
      "0": {"control_url": "https://party0.example.org:8710",
            "control_token": "<party-0-secret>", "client_host": "party0.example.org"},
      "1": {"control_url": "https://party1.example.org:8710",
            "control_token": "<party-1-secret>", "client_host": "party1.example.org"}
    }

Provision each real client runtime with only its own MP-SPDZ client certificate
and key, plus the client-I/O hosts/port configuration. The designated output
client ID is the configured client count; provision its certificate separately
to the coordinator/output runtime. Client certificates, control tokens, and
the MTD secret must come from a secret manager or deployment platform, never
from source control, YAML, or Flower fit configuration.

The party-control endpoints must use HTTPS outside loopback. The included
service does not terminate TLS; use a reverse proxy or trusted service mesh,
restrict ingress, and preserve TLS through redirects. MP-SPDZ party-to-party
and client-to-party networking must also be allowed by the deployment's
firewall, and hosts must have clocks synchronized within five minutes for
replay-protected control requests. Cross-host deployment has not been validated by this repository's
integration tests; do not treat the local demonstration as that validation.

## What the secure round does

1. Flower selects the cohort using MTD. MTD changes client participation; it
   does not assign committees.
2. The coordinator starts the same parameterized SPDZ2k circuit at every
   party. Each party compiles the packaged source and verifies its compiled
   bytecode hash matches the others.
3. Each selected client trains locally, applies configured poisoning, then
   encodes each floating-point model tensor multiplied by its sample count.
   The client sends its authenticated private input directly to all parties.
4. The Flower fit result contains no model tensors. The server verifies each
   result's Flower proxy identity, selected-client membership, and
   server-known sample count. Any missing client, failed client, malformed
   input, party error, or MAC failure aborts the secure round.
5. SPDZ2k computes the weighted sum and total sample count. Only the designated
   output client receives those values; it reconstructs the average and the
   coordinator broadcasts the new global model.
6. Every party must finish successfully. On any failure, the coordinator
   stops the parties and requests cleanup. There is no additive-sharing or
   plaintext fallback in an SMPC-enabled run.

Non-SMPC configurations explicitly use ordinary sample-weighted FedAvg and
send client model arrays to the coordinator. Individual-update robust
aggregation is supported only in this plaintext mode; enabling it together
with SPDZ2k is rejected because per-client scoring is not implemented inside
MPC.

## MTD randomness

For repeatable simulations, leaving `FL_MTD_SECRET` unset makes client
selection deterministic from the experiment seed and round. This is not
unpredictable against an adversary who knows the seed. For deployment, set a
random secret in the Flower server environment:

    export FL_MTD_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

The controller derives a round-scoped HMAC-SHA256 counter stream from this
secret and the experiment seed. The secret is not sent to clients or MPC
parties. It is not logged; experiment output records only whether secret-based
MTD was enabled.

## Security model and limitations

SPDZ2k provides malicious-secure computation with abort under its protocol
assumptions. For the configured dishonest-majority deployment, confidentiality
requires at least one aggregation party to remain honest. A party dropout,
client dropout, timeout, or protocol/MAC failure aborts the round; there is no
dropout recovery. Collusion of all parties, compromise of client or party
credentials, or compromise of the endpoint that receives the aggregate is
outside the confidentiality guarantee.

The coordinator sees the selected client IDs, participation and failure
metadata, the current global model, and the final weighted aggregate. It does
not receive individual client model tensors through Flower in SMPC mode.
Small-cohort aggregates can reveal information, especially to observers who
already know other participants' updates; the configured minimum cohort is
not differential privacy. A malicious client can submit a poisoning update:
SPDZ2k protects the computation, not whether local training or the submitted
update is honest. There is no enforceable MPC-side contribution clipping, no range proof,
differential privacy, backdoor attack-success measurement, or membership-inference
protection. Client-side clipping would not enforce a bound against a malicious
client and is not used.

See [docs/threat-model.md](docs/threat-model.md) for the trust boundaries,
assumptions, and out-of-scope threats.

## Reproducible evaluation

Run the baseline, MTD-only, SPDZ2k-only, and hybrid configurations separately
with matching experiment seeds, and use distinct output directories for each
condition. The paired multi-condition benchmark runner is available as `run_benchmark.py`.
It has not yet been used to complete the multi-seed comparison matrix. Use at
least five seeds for a future comparison and more when compute allows. Report clean test accuracy and loss, malicious client
participation, paired differences, aggregation time, party count, and
application-level SPDZ2k input bytes. These byte counts exclude transport
framing and retries; they are not total network traffic. Do not report
backdoor attack-success rates from clean test accuracy.

The historical learning rate of 0.1 caused non-finite local weights in the
five-client CIFAR-10 setup. Use `configs/benchmark_lr001/` for the stabilized
benchmark; `hybrid_verified.yaml` is the hybrid configuration.

## Output safety and robust aggregation

Experiment result filenames are restricted to one file component within the
configured output directory; traversal paths and symbolic-link output targets
are rejected. CSV exports neutralize formula-like text cells (`=`, `+`, `-`,
or `@`) while preserving numeric values.

The optional plaintext robust-update module scores client updates using
distance from the cohort median, cosine alignment, update norm, and temporal
consistency. It is a research integrity layer, not a poisoning guarantee, and
is unavailable with the sum-only SPDZ2k circuit. Differential privacy,
backdoor attack-success rate, membership inference, property inference, and
gradient inversion are outside the current evaluation.
