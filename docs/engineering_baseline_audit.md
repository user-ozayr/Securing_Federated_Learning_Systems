# Engineering baseline audit

Audit date: 2026-11-18 UTC. This is the pre-refactor baseline for the integration/simplification phase. No source modules, configurations, or evidence artifacts were moved, deleted, or edited before this report.

## Repository baseline and safety

- Worktree: `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`
- Branch: `research/spdz2k-thesis`
- HEAD: `ab2de22da9e2e4d707295b9414bbe843f375ea39`
- The worktree contains pre-existing modified and untracked implementation, configuration, documentation, evidence, and build files. These are preserved. No new branch was created because the research branch has pre-existing uncommitted work.
- Original checkout `/home/ubuntu/gemini/fl-security-research` remains on `main`, same HEAD, with the same eight modified files recorded at audit start. It was not edited.
- Baseline checks against worktree `src/`: `PYTHONPATH=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/src /home/ubuntu/gemini/fl-security-research/.venv311/bin/python -m pytest -q` at 2026-11-18 16:00:42 UTC: **71 passed, 2 Typer/Click deprecation warnings, 21.29 s**. `python -m compileall -q src tests`: pass. `git diff --check`: pass.

## Active architecture and actual execution flow

Entry points are `run_experiment.py` for one Flower experiment and `run_benchmark.py` for paired multi-configuration/multi-seed orchestration. The `--local-mp-spdz` option invokes `src/fl_security/smpc/local_demo.py`, which starts local party services, provisions temporary MP-SPDZ TLS/client material, runs Flower, then cleans up. External party deployment is also supported through environment configuration but is not cross-host validated.

For each Flower round, `ResearchStrategy.configure_fit` maps Flower proxy IDs to logical IDs, asks `MTDController` for the cohort, creates a unique round ID, checks selected-client availability, constructs `FitIns`, and starts the same parameterized party program with selected IDs and server-known partition counts. Clients load the global model, train locally, optionally receive configured research attack perturbations, validate finite tensors, multiply floating tensors by their local sample count, fixed-point encode and privately submit through MP-SPDZ ExternalIO, then return no model arrays in secure mode. The strategy resolves each result to its registered proxy, requires exactly the selected cohort, checks server-known counts and input-submitted metrics, rejects plaintext arrays, receives the aggregate/count at the designated output client, calls party completion, updates the global model, and evaluates it. Errors in secure mode cause abort/cleanup; configuration requires the exact SPDZ2k backend and has no plaintext/additive fallback.

When SMPC is disabled, the same Flower strategy receives plaintext arrays and runs weighted FedAvg or the plaintext-only `RobustUpdateDetector`. Robust scoring is explicitly rejected together with sum-only SPDZ2k. MTD is instantiated in either mode but changes selection only when enabled. The HMAC-derived schedule is secret only when `FL_MTD_SECRET` is set; without it the schedule is public-seed deterministic.

## Components, activity, and dependencies

| Component | Current role | Audit disposition |
|---|---|---|
| `federated/model.py`, `dataset.py`, `training.py` | CNN, CIFAR loading/partition, local train/evaluation | Active; retain |
| `federated/flower_simulation.py` | Single Flower workflow, client selection, attack injection, secure/plaintext aggregation branches | Active orchestrator; retain and document as canonical |
| `mtd/controller.py`, `client_selection.py`, `randomness.py` | Secret/public-seeded cohort selection | Active; one implementation split by responsibility; retain |
| `smpc/mp_spdz.py`, `mp_spdz_party_service.py`, `transport.py`, `programs/spdz2k_weighted_sum.mpc`, `fixed_point.py`, `local_demo.py` | Client I/O, party control, HTTPS policy, circuit, encoding, local launch | Active secure path; modules have distinct boundaries; do not collapse or move |
| `federated/aggregation.py` | Plaintext FedAvg only | Active only with SMPC disabled; retain |
| `federated/robust_aggregation.py` | Stateful heuristic detector plus stateless compatibility wrapper | Plaintext-only research component; not active in SPDZ2k; preserve |
| `attacks/*.py` | Configured sign-flip, label-flip and Byzantine simulation perturbations | Experimental simulation inputs, not secure defenses; preserve |
| `evaluation/*`, `logging/experiment_logger.py` | Metrics/statistics and safe result writing | Active support; retain |
| `run_benchmark.py` | Multi-config/seed experiment runner | Present and tested; README currently incorrectly says it is not included |
| MPC-BCD / norm-clipping probes | Feasibility docs and raw compiler/prototype evidence; no production `src` path | Experimental/future work; preserve artifacts; do not wire into aggregation |
| Removed additive-sharing modules | No active implementation; deletions are pre-existing worktree changes | Keep removed; do not restore |

## Configuration state

There are multiple historical/condition YAML files. The README currently names `configs/benchmark_lr001/hybrid_verified.yaml` as its integrated command. It enables MTD and SPDZ2k, uses five CIFAR-10 clients, 60% selection (three clients), four parties, fixed-point scale 1,000,000, learning rate 0.01, sign-flip simulation, and three rounds. This is a documented primary configuration, not a validated full-model run. `configs/smpc.yaml` is a separate SMPC example with MTD and attacks disabled. The direct performance harness instead used three parties and scale 100,000. Results from those direct probes must not be presented as a run of the README config.

No configuration should be deleted. Simplification should designate one primary config/command and label remaining YAML files as condition/history, not remove them.

## Existing evidence and limits

- Latest baseline full suite: 71 pass, two dependency deprecation warnings; compileall/diff checks pass. The test `test_flower_strategy_uses_active_spdz2k_and_aborts_on_client_mismatch` mocks party operations; separate saved tiny Flower integration log exercises real local parties.
- Actual tiny Flower/SPDZ2k: one synthetic 8-parameter round, three clients and parties; 16.32 s total and 0.807365 s aggregation in the chunked integration log. It is not CNN training.
- Direct deterministic production-circuit MPC passed through 100,000 parameters. At 100k: 246.236 s total, ~197 s offline/preprocessing, ~17 s online, 42,999.4 MB global party traffic. 250k hit the 300 s watchdog without output; an earlier full-shape direct attempt did likewise. Full-model Flower was not run. Compiler-only full-shape success is not runtime success.
- The 8-parameter memory-order A/B justified enabling MP-SPDZ `-M`; it does not exhaustively prove dynamic access schedules. Output receiver framing was corrected after a 10k failure; corrected 10k/50k/100k direct runs passed.
- SPDZ2k v0.4.3 is malicious security with dishonest majority and abort under protocol assumptions. Runtime passes `-e` for party SSL; experiments are loopback-only. No cross-host/key-lifecycle review or MAC-failure injection is recorded.
- MTD secret-key derivation, deterministic reuse and minimum secret length have unit coverage; existing tests verify different derived seeds, but do not yet assert that different secrets produce different selected cohorts. MTD is disabled in `configs/smpc.yaml`; the README hybrid config enables it.
- No integrated secure contribution clipping, no full attack matrix, no multi-seed results, and no MTD efficacy comparison.

## Documentation/configuration inconsistencies found

1. README says the multi-condition benchmark runner is absent, but `run_benchmark.py` exists and has tests. The paired empirical matrix itself remains unrun.
2. `docs/experimental_methodology.md` says the full model failed during a 300 s compile with ~11.3 GB RSS. That is a historical older circuit/attempt; the checked-in production circuit later compiled at 2,122,187 parameters in ~1.75 s and ~62.2 MiB. The full protocol still timed out.
3. `docs/architecture.md` draws three parties while the README hybrid config requests four; direct profile/tiny log used three. The diagram must say party count is configured.
4. Some earlier final-package material says 100k scale/party results without contrasting them against the README config (scale 1,000,000 and four parties).
5. `docs/spdz2k-implementation.md` contains a text-encoding artifact in ?configuration?s?; correct as documentation cleanup.
6. The complete integrated README command has not completed a real full-CIFAR secure round, so it must be labeled as the intended entry point, not a demonstrated successful full model.

## Simplification decision

The active secure data path is already singular: Flower ? MTD cohort ? local training ? SPDZ2k private input ? aggregate-only output ? global model update. No duplicated active secure aggregation backend was found. Keep the distinct client helper, party control service, transport policy, circuit, and local launcher modules because they cross separate trust/lifecycle boundaries. Keep robust update detection only on the explicit plaintext branch. Keep attack and clipping code/evidence as experimental. Simplify by clarifying the one primary configuration, correcting stale documentation, and adding a focused MTD secret-separation regression test; avoid broad directory moves or deleting historical configs.
