# Final Architecture — Hybrid SPDZ2k + MTD Federated Learning Framework

Codebase: `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`, branch
`research/thesis-completion` (from `research/spdz2k-thesis` @ `5c7b497`).
Single entry points: `run_experiment.py` (one run), `run_suite.py` (evaluation
grid), `run_mpc_validation.py`, `run_mpc_benchmark.py`, `run_mtd_exposure.py`,
`analyze_suite.py`.

## 1. Components

```
┌──────────────────────────── Flower coordinator (server) ─────────────────────────────┐
│ ResearchStrategy (flower_simulation.py)                                               │
│   configure_fit ── MTDController.generate_round_config(r)  ──► cohort C_r             │
│        │             schedule: static | deterministic | secret (HMAC-SHA256 PRF)      │
│        ├─ sum-only:  start_round(program=weighted_sum)                                │
│        └─ robust:    weights w_k, spec ◄─ SecureDefenceConfig.round_spec()  (budget)  │
│                      start_round(program=robust_aggregate, weights, spec, chunk)      │
│   aggregate_fit ── identity/count/completeness checks ── receive outputs ──           │
│        decode_robust_output() ── output-norm check ── apply_delta() ── finish_round   │
│   evaluate ── clean accuracy, loss, backdoor ASR, per-round metrics (CSV)             │
└───────────────┬──────────────────────────────────────────────┬────────────────────────┘
   HMAC-signed control (start/status/stop/cleanup)             │ output client (TLS cert)
                ▼                                              ▲
┌──────────── Party service ×3 (mp_spdz_party_service.py) ────┴──────────────────────────┐
│ validate payload → generate source (+ROUND_ARGUMENTS) → compile (-R 64 -M) → hash →   │
│ launch spdz2k-party.x → journals (round IDs, request IDs) → status incl. MP-SPDZ      │
│ measured time/traffic → cleanup (all tapes)                                           │
│ programs/spdz2k_weighted_sum.mpc       Σ n·w, Σ n               (unchanged)           │
│ programs/spdz2k_robust_aggregate.mpc   norms, median, clip/screen, Σ a·C·w·x          │
└──────────────▲─────────────────────────────────────────────────────────────────────────┘
               │ client input (TLS client certificate, Damgård et al. triple masking)
┌──────────────┴──────────── Flower clients (Ray actors) ───────────────────────────────┐
│ ResearchNumPyClient.fit: local SGD → [attack: data poisoning (label flip, backdoor)    │
│ and/or update manipulation (sign flip, boost, noise, adaptive scaling)]               │
│   sum-only: submit_client_update(n·w)        robust: submit_client_delta(Δ·2^f)       │
│ returns no tensors in SMPC mode; plaintext modes return tensors to FedAvg/defences    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Plaintext comparison paths (no cryptography, used only as baselines/references):
FedAvg (`aggregation.weighted_fedavg`), the robust detector
(`robust_aggregation.RobustUpdateDetector`), and `defences.norm_defence_reference`
(the same integer algorithm as the robust program, executed in plaintext).

## 2. Data flow of one robust secure round

```
coordinator                      parties P0,P1,P2                     client k ∈ C_r
-----------                      ----------------                     -------------
cohort C_r ← MTD(r)
w_k ← quantise(n_k); spec ← budget-checked
start(round_id, ids, n, w, spec) ──► validate, compile, hash ──► hashes equal? else abort
FitIns(global model, robust cfg) ────────────────────────────────────────────► train, attack?
                                                                               x_k = round(Δ_k·2^f)
                                  ◄──── [n_k, x_k] (masked by triples) ────────  submit_client_delta
                                  R_k, S_k, valid_k, T, a_k, C_k, A (inside MPC)
receive_robust_result ◄─── [T, #clipped, a, flags, A] (output client only)
decode Δ̄ = A / (2^(g+f) Σ a_k w_k);  ‖A‖² ≤ (2^g Σ a w)² B ?  → apply or keep model
finish_round → per-party MP-SPDZ statistics (protocol s, MB)
```

## 3. Interfaces

| Interface | Location | Contract |
|---|---|---|
| `start_round(parties, round_id, client_ids, input_count, expected_counts, output_client_id, port_base, *, program, weights, robust_spec, chunk_size)` | `smpc/mp_spdz.py` | concurrent authenticated start; all bytecode hashes must match; any failure → abort all |
| `submit_client_delta(local, global, n, client_id, *, hosts, port_base, credentials_dir, mp_spdz_home, fractional_bits, chunk_size)` | `smpc/mp_spdz.py` | encodes `Δ` at `2^f`, rejects NaN/∞ and values ≥ 2⁶², sends `[n, x…]` in chunks |
| `submit_wire_values(...)` | `smpc/mp_spdz.py` | raw ring elements (robustness testing only) |
| `receive_robust_result(...)` → `RobustResult` | `smpc/mp_spdz.py` | reads `2+2K+d` values; decision values must be 0/1 |
| `finish_round(...)` → `[{party_id, protocol_seconds, party_data_sent_mb, party_rounds, global_data_sent_mb}]` | `smpc/mp_spdz.py` | waits for exit code 0 at every party, cleans up |
| `SecureDefenceConfig` | `smpc/robust.py` | mode `clip/screen/clip_screen`, threshold `static/adaptive`, `f`, `g`, weights, bounds; `round_spec()` validates the 2⁶² budget and the output margin |
| `robust_reference(inputs, weights, spec)` | `smpc/robust.py` | bit-exact emulation of the MPC program |
| `decode_robust_output(result, weights, config)` | `smpc/robust.py` | decoding + exact integer output-norm check |
| Party control HTTP API | `smpc/mp_spdz_party_service.py` | `POST /v1/rounds/{id}/{start,status,stop,cleanup}`, HMAC-SHA256 over method/route/timestamp/request-ID/body, ±300 s, replay journal |
| `MTDController(config).generate_round_config(r, N, fraction)` | `mtd/controller.py` | `mtd.schedule` explicit; `secret` requires `FL_MTD_SECRET` ≥ 32 bytes |
| `predicted_schedule`, `predictive_set`, `just_in_time_assignment`, `exposure_metrics` | `mtd/exposure.py` | adversary models for schedule predictability |
| `ByzantineAttacker` | `attacks/byzantine.py` | attack types and placements (see `THREAT_MODEL.md`) |

## 4. Configuration schema (YAML)

```yaml
experiment: {name: str, seed: int, rounds: int}
federated_learning:
  framework: flower
  dataset: fashion_mnist | mnist | cifar10
  model: compact_cnn | cifar10_cnn
  num_clients: int
  fraction_train: float          # K = int(N * fraction)
  local_epochs, batch_size, learning_rate
  partitioning: iid | label_sorted | dirichlet   # dirichlet_alpha
mtd: {schedule: static | deterministic | secret}  # or legacy enabled/selection_strategy
smpc:
  enabled: bool
  backend: mp_spdz_spdz2k
  num_aggregation_parties: int   # >= 2
  min_clients_per_round: int
  fixed_point_scale: int         # sum-only program
  defence:                       # robust program (optional)
    enabled: bool
    mode: clip | screen | clip_screen
    threshold: static | adaptive
    static_norm, min_norm, max_norm, max_valid_norm: float
    median_multiplier_squared, screen_multiplier_squared: int
    fractional_bits: int (14), clip_bits: int (8)
    weighting: uniform | sample, weight_bits: int
    reveal_client_flags: bool, chunk_size: int, use_edabits: bool
defences:                        # plaintext comparisons only
  robust_aggregation: {...}
  norm_defence_reference: {same keys as smpc.defence}
attacks:
  enabled: bool
  attack_type: label_flip | sign_flip | random_noise | scaled_replacement | backdoor | adaptive_backdoor
  num_malicious | compromised_fraction, placement: random | stratified | predictive
  adversary_model: predictive | just_in_time      # schedule-aware adversaries
  strength, boost, adaptive_norm_fraction
  backdoor: {target_label, trigger_size, poison_fraction}
evaluation: {output_dir, save_csv, save_plots, instrumentation, measure_backdoor_asr}
```

## 5. Deployment modes

* **Local evaluation (validated):** `local_spdz2k_environment()` starts one
  party service per party on 127.0.0.1 with temporary TLS material; clients are
  Ray actors on the same host.
* **Distributed (documented, not validated here):** one party service per host
  (`python -m fl_security.smpc.mp_spdz_party_service`), HTTPS termination in
  front of the control API, `FL_MPSPDZ_PARTIES_JSON` on the coordinator, client
  certificates provisioned per client runtime (see README).

## 6. What changed relative to the starting point

See `IMPLEMENTATION_REPORT.md` for the file-level record. Key architectural
additions: the robust SPDZ2k program and its coordinator/reference module;
explicit MTD schedules and adversary models; compact model/dataset options;
new attacks; per-round measured MPC statistics; the resumable evaluation suite.
The sum-only SPDZ2k path, the control-plane security mechanisms and the
plaintext detector are preserved unchanged in behaviour.
