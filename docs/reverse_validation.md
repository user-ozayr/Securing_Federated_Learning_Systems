# Reverse validation

Review date: 2026-11-18. Each property is traced from the claim back to implementation, test, and evidence. “Pass” is limited to the tested scope; it is not a formal cryptographic proof.

| Claimed property | Required implementation | Test or experiment | Evidence | Status |
|---|---|---|---|---|
| Secret-seeded MTD | HMAC-SHA256-derived schedule from `FL_MTD_SECRET`; deterministic round scope | `test_mtd_controller_uses_secret_keyed_schedule`, `test_different_mtd_secrets_can_change_the_selected_cohort`, `test_missing_mtd_secret_is_public_seed_deterministic`, `test_secret_seed_requires_sufficient_entropy` | Full suite passed 77 tests; test covers deterministic reuse, different cohort for selected fixtures, unset-secret public behavior, and short-secret rejection | Pass (schedule logic only; not proof of client honesty) |
| Cohort integrity | `configure_fit` chooses before training; proxy/ID checked; selected IDs and expected counts included in round-specific party program identity; circuit checks only selected/unique inputs | `test_flower_rejects_unregistered_or_unselected_proxy_results`, `test_program_identity_binds_round_cohort_and_expected_counts`, Flower missing-cohort path in `test_flower_strategy_uses_active_spdz2k_and_aborts_on_client_mismatch` | Full suite passed; raw direct successful MPC runs validate normal cohort/count path. Unexpected wire-level party connection was not injected into live MPC | Pass (unit/normal path; no malicious wire-level injection) |
| Secure aggregation | Production `spdz2k_weighted_sum.mpc`, authenticated ExternalIO, weighted fixed-point encoding, aggregate-only output, `-M` compile | `test_weighted_model_encoding_includes_sample_count_and_float_tensors`, output framing/count tests; direct three-party known-answer runs | Exact Python-reference match through 100k; tiny real Flower run; 250k/full-size timed out without aggregate | Pass through measured sizes; full-model status is Fail/Incomplete |
| Individual-update confidentiality | Flower returns empty arrays in secure mode; ExternalIO private input; circuit reveals only sum/count to output client | `test_output_client_receives_only_weighted_average_and_count`, code/data-flow review, tiny actual Flower log | Strategy rejects plaintext fit arrays; the MP-SPDZ circuit uses private client input and output-client reveal; same-host integration passed | Partial (implementation path supported; no formal noninterference proof, cross-host test, or compromised-host protection) |
| Contribution bounding | Enforceable MPC-side clipping or rigorously validated alternative | Existing compiler probes and 2D clipping prototype only; no active production-path test | `docs/contribution_clipping_decision.md` records Option C; no client-side clipping substitution | Not implemented |
| Global model correctness | Decode weighted average, preserve integer buffers, validate total/tail, update Flower global state after all parties finish | Direct deterministic probes; `test_flower_strategy_uses_active_spdz2k_and_aborts_on_client_mismatch`; tiny real Flower run | Direct vector max error 0 at completed sizes; tiny synthetic Flower round passed; no full CNN round | Pass (synthetic/tested sizes only) |
| No insecure fallback | Exact backend check, plaintext parameter rejection, abort/cleanup on error; plaintext FedAvg only when SMPC disabled | `test_secure_config_rejects_unsupported_or_missing_backend`, Flower mismatch/omission tests, `test_round_start_failure_triggers_abort_and_cleanup` | Full suite passed; code path review confirms no additive/plaintext fallback when enabled | Pass (tested control paths; live malicious MAC failure was not injected) |
| Replay and reused-round rejection | HMAC signature, timestamp window, unique request ID journal, round-ID journal | `test_party_control_authenticates_and_rejects_replayed_requests`, `test_control_request_replay_journal_survives_service_restart`, `test_party_service_rejects_reused_round_id` | HTTP unit tests and persistent journal tests passed | Pass (unit/service level) |

## Check 1: Security claims

The README, architecture, threat-model and security-limitations docs now state that contribution clipping is absent, robust individual-update screening is plaintext-only, MTD does not establish client honesty, and full-model/cross-host/attack-resistance claims are unvalidated. The party service launches MP-SPDZ with `-e`; local setup provisions SSL material, but the evidence is loopback-only. SPDZ2k is described under MP-SPDZ v0.4.3 malicious dishonest-majority assumptions with abort, not availability. A failed MAC has not been injected experimentally.

## Check 2: Data flow

1. Flower maps the registered proxy to a logical client and chooses a cohort before fit. The configured HMAC secret is held by the coordinator process; the secret value is not sent in `FitIns` or recorded in result CSVs. Selected client IDs and whether secret seeding was enabled are observable metadata.
2. Selected clients receive the global model and train locally. Plaintext updates exist in the client process. Configured attacks perturb local training/update before secure encoding.
3. In secure mode, client helpers encode floating tensors times sample count, put count first, pad to 1,024-value messages, and send through MP-SPDZ ExternalIO. Flower fit results return empty model arrays.
4. Each party receives only its protocol share under SPDZ2k assumptions. Parties know circuit, selected IDs, expected sample counts and public round metadata. The circuit opens a per-client equality/mismatch result for count binding; mismatch aborts.
5. The designated output client receives weighted sum and total count, verifies expected count and padding, decodes the average, and Flower updates/broadcasts the global model. The coordinator still sees client IDs, participation/failure status, counts, current model and final aggregate. Repeated aggregates may permit inference.
6. Experiment output records aggregate metrics and metadata, not individual update arrays or the MTD secret. Same-host process/kernel isolation is not provided.

## Check 3: Failure validation

| Failure | Existing validation | Result / remaining limit |
|---|---|---|
| Missing selected client | Flower strategy test calls `aggregate_fit` with an omitted result | Rejects and aborts in mocked strategy path; no live client dropout experiment |
| Unexpected/unregistered Flower client | `_resolve_authenticated_client_ids` tests | Rejected |
| Wrong client-reported count | Flower strategy test; output total-count test | Rejected |
| Duplicate round ID | `test_party_service_rejects_reused_round_id` | Rejected at service start; journal persistence code reviewed |
| Replayed control request | HTTP/restart journal tests | Rejected |
| Invalid MPC output | Truncated array, nonzero tail and wrong total tests | Rejected by output helper; not injected by a live party |
| Party startup failure | `test_round_start_failure_triggers_abort_and_cleanup` | Mocked failure triggers abort; 250k watchdog run separately confirmed process cleanup |
| Malformed count/input framing | Encoder/chunk helper tests and corrected 10k framing regression | Invalid helper inputs rejected; one real framing error was corrected; arbitrary malformed wire payload not injected |
| Numerically out-of-ring input | `test_weighted_model_encoding_rejects_ring_overflow` | Rejected before MPC submission |
| Over-bound but in-ring contribution | No clipping/bound enforcement exists | Not implemented; client can submit arbitrary in-range values |
| MPC MAC failure / malicious party / network partition | None | Not tested; protocol should abort, but no experiment proves this implementation path |

## Check 4: Regression validation

Baseline before changes: 71 passed, 2 warnings. After the targeted test/documentation updates: **77 passed, 2 warnings** in 5.50 s; focused set 30 passed in 5.48 s. `compileall` and `git diff --check` pass. The original checkout remains on `main` at the same HEAD and retains its same eight pre-existing modified files.

## Check 5: Reproducibility validation

The reproducibility guide provides test, compile, wheel and profile-harness commands with pinned paths/versions. The preserved profile harness supports the tested synthetic direct sizes. The README primary command names `configs/benchmark_lr001/hybrid_verified.yaml`, but a full CIFAR Flower round has not been completed; therefore clean-environment reproduction of the primary full-model experiment is **not validated**. The direct performance profile uses three parties and scale 100,000, whereas that YAML requests four parties and scale 1,000,000.

## Check 6: Documentation consistency

README and architecture docs now identify the same primary YAML and state that clipping is absent. Methodology distinguishes full-circuit compilation from full-protocol execution, identifies the existing benchmark runner, and records differing direct-profile settings. Historical configuration variants and output artifacts are retained. The README primary command is intended workflow, not a verified full-size success.
