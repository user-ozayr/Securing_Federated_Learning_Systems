# Securing Federated Learning with MTD and MP-SPDZ

Research prototype for horizontal federated learning, Moving Target Defence
(MTD), poisoning experiments, and secure aggregation using MP-SPDZ v0.4.3
with the SPDZ2k protocol – including an integrity defence that runs **inside**
the secure computation (per-client L2 clipping and norm screening with an
adaptive, median-based threshold; see `docs/secure_robust_aggregation.md`).

Entry points: `run_experiment.py` (one run), `run_suite.py` (evaluation grid),
`analyze_suite.py` (tables/figures), `run_mpc_validation.py` (SPDZ2k vs exact
reference), `run_mpc_benchmark.py` (SPDZ2k cost), `run_mtd_exposure.py`
(schedule predictability), `run_leakage_study.py` (gradient inversion against
individual updates vs the SPDZ2k aggregate). Setup and reproduction:
`docs/reproduction.md`.
Completion evidence and reports: `research_output/completion/`.

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

With `smpc.defence.enabled: true` the round uses
`spdz2k_robust_aggregate.mpc` instead: clients submit their update
`w_local − w_global` at scale `2^f`; inside SPDZ2k the parties compute each
client's squared norm, an optional lower-median threshold, screening (revealed
accept bit) and/or clipping with secret coefficients, and reveal only the
clipped weighted sum, the threshold and declared flags. The coordinator checks
the aggregate norm before applying the update; a failed check keeps the
previous model (only possible with malformed, wrapping inputs).

Non-SMPC configurations explicitly use ordinary sample-weighted FedAvg and
send client model arrays to the coordinator. The plaintext detector
(`defences.robust_aggregation`) and the plaintext execution of the norm defence
(`defences.norm_defence_reference`) are baselines for comparison only; the
plaintext detector cannot be combined with SPDZ2k because its per-client scoring
needs individual updates.

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
update is honest. The optional in-MPC defence bounds each accepted client's
contribution (clipping/screening); it does not remove poisoning whose update
looks honest in magnitude, and colluding clients that deviate from the encoding
can exceed the per-client bound (the output check still bounds the applied
update). There are no per-coordinate range proofs, no differential privacy and
no membership-inference protection. Client-side clipping would not enforce a
bound against a malicious client and is not used.

See [docs/threat-model.md](docs/threat-model.md) for the trust boundaries,
assumptions, and out-of-scope threats.

## Reproducible evaluation

The completion evaluation is defined in `src/fl_security/experiments/grid.py`
(Fashion-MNIST, 2,202-parameter CNN, 12 clients, 4 per round, 3 seeds; six core
configurations from FedAvg to SPDZ2k + secure defence + MTD; six attack
scenarios including a trigger backdoor with attack-success rate; adaptive,
MTD-predictability, sweep and non-IID studies). Run it with `run_suite.py`
(resumable, one process per run) and aggregate with `analyze_suite.py`.
Per-round CSVs report clean accuracy and loss, backdoor ASR, malicious
participation, defence decisions, round time, MP-SPDZ-measured protocol time and
global traffic, and application-level input bytes. Methodology:
`docs/experimental_methodology.md`. The older paired runner `run_benchmark.py`
remains available.

Results of the completion evaluation (228 runs, same-host deployment) are in
`research_output/completion/FINAL_VALIDATION_REPORT.md`; limitations are listed
in `research_output/completion/SECURITY_LIMITATIONS.md`. In short:

* **Exactness.** The SPDZ2k robust program is bit-exact against its reference.
* **Secure aggregation alone.** Sum-only SPDZ2k does not reduce poisoning.
* **The in-MPC clip+screen defence** mitigated magnitude-based attacks and a
  boosted backdoor (ASR 0.017) without rejecting honest IID clients. It
  mitigated label flipping and an adaptive at-the-bound backdoor only partly
  (ASR up to 0.35).
* **MTD** removed schedule predictability but is not a poisoning defence.
* **Cost.** A secure round with the defence costs 3.7× a FedAvg round at 2,202
  parameters.

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
is unavailable with SPDZ2k. Differential privacy, membership inference and
property inference are outside the current evaluation. Gradient inversion was
measured for single-step updates (E6): secure aggregation hides which client an
image came from, but the aggregate of a small cohort can still contain exact
copies of individual training images.
