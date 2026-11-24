# Migration assessment: SPDZ2k integration

Assessment date: 2026-11-18 (Europe/Budapest)

## Scope and safeguards

- Remote repository: `/home/ubuntu/gemini/fl-security-research`
- Branch and base: `main`, `ab2de22da9e2e4d707295b9414bbe843f375ea39`
- The original checkout was not modified during this assessment.
- The real source for the proposed migration is the directory `spdz2k-integration-worktree-3f9277d5`, not its nested `snapshot.tar.gz`. The nested archive is stale and includes legacy additive-sharing code.
- The remote checkout has eight unstaged tracked modifications, no staged changes, and no untracked files.

## Preservation and backup verification

A recoverable backup was created outside the repository at:

`/home/ubuntu/gemini/backups/fl-security-research-stage1-20261118/`

It contains `repository.bundle` and `existing-worktree.patch`. `git bundle verify` succeeded. The patch is 22,814 bytes; its SHA-256 is `049710ac5b263208bd420aff21fa517827fb11c6e48d054811fbfca8e9477fa7`. That digest matches both a fresh remote `git diff --binary` and the stored patch. `git apply --check --reverse` against the existing modified working tree and `git apply --cached --check` against the indexed base both succeeded. The bundle records all 10 current refs, including the main and research branches and stash.

The patch can therefore restore the eight current tracked modifications on top of the recorded base. There are no current untracked files to preserve. Tracked experiment outputs and the CIFAR-10 data are in the repository and remain in the original checkout; the integration snapshot does not contain them.

## Remote environment and existing artifacts

- System Python: 3.14.4.
- Project `.venv311`: Python 3.11.18.
- Installed in `.venv311`: PyTorch 2.15.0, torchvision 0.29.2, Flower 1.38.0, NumPy 2.4.6, pandas 3.1.1, PyYAML 6.0.3, pytest 9.2.0, matplotlib 3.11.2.
- Not installed in `.venv311`: `flwr-datasets`, `pytest-cov`, `coverage`, `scipy`; no installed distribution named `mp-spdz` was found. MP-SPDZ is expected to be an external source/build and must be checked separately.
- The venv has no `pip` module, so use its installed package tooling or the project’s documented environment manager rather than assuming `python -m pip` works.
- Existing tracked data includes CIFAR-10 extracted batches and a 170,498,071-byte archive. Existing results include baseline, MTD, hybrid, prototype-SMPC, robust-detection, tuned robust-detection, and five-seed benchmark outputs, plus logs, CSVs, reports, and PNGs. Preserve all of these; do not overwrite historical results.

## File-by-file migration comparison

| File or file group | Remote version | Snapshot version | Existing modifications | Recommended action |
|---|---|---|---|---|
| `README.md` | Documents additive sharing, its security limitations, credential scoping, transport hardening, and historical benchmark instructions. | Replaces the additive architecture with SPDZ2k-only claims and local/cross-host distinctions. | README is one of the eight modified files; the current hardening content is in the backup patch. | Replace obsolete protocol instructions, while carrying forward the credential, transport, MTD-secret, and honest limitation guidance where still applicable. Verify each claim against the integrated implementation. |
| `configs/*.yaml`, `configs/benchmark_lr001/*.yaml`, `configs/robust/*.yaml` | Contains the established baseline, experiment, and robust-detector configurations. Several files remain remote-only. | Updates SMPC configurations to the SPDZ2k backend and removes committee-era fields. | No config file is among the eight current modified files. | Apply snapshot updates only to matching secure configurations. Keep remote-only baseline and historical experiment configurations. Review every secure config with the new validator. |
| `docs/threat-model.md` | Threat model covers the prior additive service. | Rewrites the threat model for SPDZ2k and distinguishes local demonstration from separate-host deployment. | No current uncommitted change to this file. | Use as the SPDZ2k baseline; independently verify protocol assumptions and add explicit MPC-BCD limitations later. |
| `pyproject.toml` | Existing dependencies, packaging, and console/test configuration. | Adds MPC circuit package data and updates supported dependencies/entry points. | No current uncommitted change. | Merge metadata carefully, retain remote experiment dependencies and scripts, and verify the built wheel contents. |
| `run_experiment.py` | Supports the original experiment and local aggregator workflow. | Adds the local MP-SPDZ launcher option. | One of the files that differs; not in the eight modified paths. | Integrate the SPDZ2k option while retaining existing non-secure experiment behavior. Do not make secure failure fall back to FedAvg. |
| `src/fl_security/config.py` | Accepts legacy SMPC/committee settings. | Rejects unsupported secure backends and dropout-recovery options. | No current uncommitted change. | Adopt the SPDZ2k validation and test it against both preserved and migrated YAML configs. |
| `src/fl_security/federated/aggregation.py` | Includes FedAvg and legacy secure aggregation helpers. | Retains plaintext FedAvg only for explicitly non-secure runs. | No current uncommitted change. | Use snapshot behavior; verify secure strategy cannot call plaintext aggregation after errors. |
| `src/fl_security/federated/flower_simulation.py` | Current working file includes result identity checks, duplicate logical-client rejection, and hardening from the existing patch, alongside additive-sharing flow. | Replaces additive shares with weighted SPDZ2k input/output and retains identity/duplicate checks. | Modified remotely; patch adds security checks. | Reconcile by retaining identity, duplicate, server-known sample-count, and failure checks while replacing only the aggregation protocol. Review each error and cleanup path. |
| `src/fl_security/mtd/controller.py` | Selects clients and may assign legacy committees. | Removes committee generation and selects participants for SPDZ2k rounds. | No current uncommitted change. | Adopt snapshot selection semantics; preserve reproducible/secret-seeded scheduling and test MTD with the new backend. |
| `src/fl_security/smpc/fixed_point.py` | Includes legacy field decoding/encoding behavior. | Uses SPDZ2k ring-range-safe fixed-point encoding and removes finite-field decoding. | No current uncommitted change. | Adopt after independently checking scale, rounding, signed ring range, and overflow behavior. |
| `src/fl_security/smpc/local_demo.py` | Starts hardened local additive aggregation services. | Starts local MP-SPDZ party services, creates temporary credentials/runtime files, and cleans up. | Modified remotely; patch contains service-launch hardening. | Replace the obsolete launcher in the worktree. Carry forward environment isolation, robust cleanup, and secret handling where applicable; test cleanup on both success and failure. |
| `src/fl_security/smpc/mp_spdz.py` | Absent. | New party configuration, client I/O, weighted input encoding, status, completion, abort, and bytecode checks. | No existing change. | Add; inspect all endpoints, protocol behavior, input validation, output visibility, and cleanup. |
| `src/fl_security/smpc/mp_spdz_party_service.py` | Absent; prior `aggregator_server.py` provides authenticated HTTP control for the old protocol. | New per-party process service with signed, timestamped, replay-protected controls. | Existing `aggregator_server.py` has security changes in the backup patch. | Add the new service and audit equivalent protections. Do not carry forward obsolete additive endpoints as a fallback. |
| `src/fl_security/smpc/programs/spdz2k_weighted_sum.mpc` | Absent. | New weighted-sum SPDZ2k circuit. | No existing change. | Add and inspect against MP-SPDZ v0.4.3 compiler/runtime semantics before claiming security or numerical correctness. |
| `src/fl_security/smpc/transport.py` | Transport helpers are located with the additive aggregator service. | Shared transport validation is separated from the deleted service. | `aggregator_server.py` has an existing transport-hardening modification. | Adopt and verify HTTPS/loopback constraints at the new client/party boundaries. |
| `src/fl_security/smpc/additive_sharing.py` | Present. | Absent. | Not among the eight modified paths. | Remove from the active integrated source after references and package contents are checked; retain the original in the backup bundle. |
| `src/fl_security/smpc/aggregator_server.py`, `client_sharing.py` | Present and currently modified by hardening work. | Absent. | Both are among the eight modified paths. | Treat as obsolete protocol implementation. Preserve their patch in the backup; migrate still-relevant authentication/transport invariants into the SPDZ2k services, then remove from the active branch. |
| Tests `test_distributed_smpc.py`, `test_sharing.py`, `test_secure_aggregation.py` | Cover the additive implementation; `test_distributed_smpc.py` also has a current uncommitted modification. | Removed or replaced by SPDZ2k tests. | `test_distributed_smpc.py` is in the backup patch. | Replace only after equivalent security requirements are covered by the new control, client-I/O, Flower, and MPC tests. Keep unrelated test coverage. |
| `tests/test_flower_secure_smoke.py` | Tests the Flower/additive-party path, including hardening of client identity and sample counts. | Tests Flower with SPDZ2k inputs and no client tensors in `FitRes`. | Modified remotely. | Replace the protocol-specific fixture, retaining identity, server-known counts, no-plaintext, abort, and cleanup assertions. |
| `tests/test_security_hardening.py` | Includes existing identity, authentication, CSV safety, MTD, and transport hardening tests. | Removes additive-only tests and updates remaining checks to SPDZ2k; adds duplicate-result coverage. | Modified remotely. | Reconcile test-by-test. Retain all protocol-independent hardening and add tests for SPDZ2k request authentication, replay journal, malformed input, and cleanup. |
| `tests/test_configs.py`, `test_hybrid_pipeline.py`, `test_integration.py`, `test_mtd.py`, `test_mtd_committee_privacy.py`, `test_mtd_execution.py` | Cover original config, pipeline, and committee behavior. | Update for SPDZ2k-only config and committee-free MTD. | No current uncommitted changes to these paths. | Adopt snapshot updates while retaining unrelated test scenarios and adding coverage for expected MTD/SPDZ2k interactions. |
| `tests/test_mp_spdz.py`, `tests/test_mp_spdz_control.py` | Absent. | New client/circuit and control tests. | No existing change. | Add and run in the project Python 3.11 environment; distinguish mocked unit checks from actual protocol tests. |
| Remote-only `run_benchmark.py`, `run_all.sh`, `experiments/`, `data/`, `results/`, `.github/`, and baseline/config variants | Present in the research checkout. | Mostly absent from the snapshot. | No unstaged changes reported. | Preserve. Do not replace the repository with the snapshot tree or delete these paths. Keep benchmark tooling and raw/historical results available for the thesis work. |

## Migration strategy

1. Keep the original `main` checkout untouched.
2. Use the verified Git bundle and patch as the recovery point.
3. Create a separate worktree from `ab2de22` on a new research branch and apply the eight-file patch there.
4. Migrate from the actual snapshot directory file-by-file, preserving remote-only benchmark tooling, configurations, data, and results.
5. Reconcile overlapping hardening explicitly; remove the obsolete additive implementation only in the isolated worktree after replacement coverage is present.
6. Run focused tests and the complete test suite in `.venv311`; inspect and validate MP-SPDZ v0.4.3 independently before protocol claims.
7. Do not commit or push without explicit authorization.

## Assessment conclusion

The backup is verified and the source snapshot has been identified correctly. A safe isolated migration is feasible. The changes are not yet migrated, tested, or validated end-to-end. The snapshot does not implement MPC-BCD; that is a separate research feature and must be evaluated after the SPDZ2k migration works.
