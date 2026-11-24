# Initial Repository Audit — "Securing Federated AI Systems"

Audit date: 2026-11-19 (UTC). Host: `oracle-vnic-3`, Ubuntu (aarch64, ARM Neoverse-N1), 3 vCPU, 17 GiB RAM, no swap, no GPU, 8.9 GB free disk at audit time.
Interpreter used for all checks: `/home/ubuntu/gemini/fl-security-research/.venv311/bin/python` (Python 3.11.18; torch 2.15.0, torchvision 0.29.2, flwr 1.38.0, ray 2.55.1, numpy 2.4.6, pandas 3.1.1; **no scipy, no pip**).

All statements below were verified against the source tree, Git metadata, test runs, and stored evidence on the host. Where an earlier report made a claim, the claim is re-checked rather than repeated.

---

## 1. What the two "repositories" actually are

| | Repository A | Repository B |
|---|---|---|
| Path | `/home/ubuntu/gemini/fl-security-research` | `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis` |
| Git status | **Main worktree** of the repository | **Linked worktree** of the same repository (`.git` file → `fl-security-research/.git/worktrees/fl-security-research-spdz2k-thesis`) |
| Branch / HEAD | `main` @ `ab2de22` (= `origin/main`, merge of PR #1) | `research/spdz2k-thesis` @ `5c7b497` (= `origin/research/spdz2k-thesis`) |
| Relationship | — | exactly **one commit** ahead of `main`: "feat: migrate federated secure aggregation to MP-SPDZ SPDZ2k" (84 files, +3,692 / −2,632) |
| Remote | `git@github.com:user-ozayr/Securing_Federated_Learning_Systems.git` (shared) | same |
| Uncommitted state | 8 modified tracked files (README, `flower_simulation.py`, `smpc/aggregator_server.py`, `smpc/client_sharing.py`, `smpc/local_demo.py`, 3 tests). Byte-identical (SHA-256 `049710ac…`) to the earlier backup `backups/fl-security-research-stage1-20261118/existing-worktree.patch`. | Tracked tree clean; 163 untracked research-evidence files under `research_output/`; one stray directory whose name is a mangled shell command (`" \ && { echo 'UTC:'; …"`) containing only empty nested directories — an artefact of an earlier broken command, preserved untouched. |
| Ignored data | `.venv311` (5.9 GB), `venv` (6.1 GB, Python 3.14.4), `data/` (CIFAR-10, 341 MB), `results/` (1.3 MB) | — |

Other branches: `research/integrate-hybrid-pipeline` (`dd75ecc`, merged into `main`), `research/robust-poisoning-defense` (`32fee8f`, merged via the hybrid branch), `backup/integrate-hybrid-pipeline-before-rebase` (`d210f3d`).

Out of scope (inspected, not modified): `/home/ubuntu/fl-security-research` is an older, unrelated repository (`FL_Security.git`, single "Initialize" commit). It contains raw MNIST files only.

**Consequence:** "integrating the two repositories" is a branch-level question, not a code merge between unrelated projects. Repository B already contains everything in A's committed `main` except the old custom SMPC, which B intentionally replaced with SPDZ2k.

## 2. Architecture of Repository A (`main`)

```
src/fl_security/
  attacks/      byzantine.py (ByzantineAttacker), label_flip.py, sign_flip.py
  federated/    flower_simulation.py, aggregation.py (weighted FedAvg), robust_aggregation.py,
                dataset.py (CIFAR-10; iid / label_sorted), model.py (CIFAR10CNN), training.py
  mtd/          controller.py, client_selection.py, randomness.py (HMAC counter PRF)
  smpc/         additive_sharing.py, aggregator_server.py, client_sharing.py,
                fixed_point.py, local_demo.py   ← custom additive secret sharing
  evaluation/   metrics.py, statistics.py, csv_safety.py
  logging/      experiment_logger.py
run_experiment.py, run_benchmark.py, run_all.sh, configs/ (baseline, mtd, smpc, hybrid, robust/, benchmark_lr001/)
```

* **SMPC in A** is a project-specific additive secret-sharing protocol over the prime field 2⁶¹−1 with HTTP aggregator services, MTD-rotated "committees", and a second-stage re-sharing step. It is not SPDZ2k and has no MAC-based malicious security.
* **Uncommitted changes in A** harden this custom SMPC further. They touch modules that B deletes, so they cannot be meaningfully merged into the SPDZ2k design; they are preserved as backups (see §8).
* **Tests:** `71 passed` (8.9 s) on the current working tree, 2026-11-19.

## 3. Architecture of Repository B (`research/spdz2k-thesis`)

```
Flower simulation (start_simulation, custom Strategy)          ← coordinator / server
  ├─ MTDController ──► round-scoped HMAC-SHA256 counter PRF ──► selected cohort
  ├─ ResearchNumPyClient.fit(): local SGD → optional attack → encode n·w (fixed point)
  │      └─ mp_spdz.submit_client_update() ── TLS (client cert) ──► every party's client port
  ├─ mp_spdz.start_round()/finish_round()/abort_round() ── HMAC-signed HTTP control ──►
  │      MPSpdzPartyService (one per party): compile spdz2k_weighted_sum.mpc with round args,
  │      compare bytecode SHA-256 across parties, launch spdz2k-party.x, round-ID + request-ID journals
  └─ mp_spdz.receive_weighted_average(): output client receives Σ nᵢwᵢ and Σ nᵢ → new global model
MP-SPDZ v0.4.3 (/home/ubuntu/gemini/MP-SPDZ-v0.4.3, spdz2k-party.x, ring Z_2^64, s = 64)
```

Key properties verified in code:

| Property | Where | Verified behaviour |
|---|---|---|
| Sum-only weighted aggregation | `smpc/programs/spdz2k_weighted_sum.mpc` | Clients send `count, n·w₁…n·w_d` padded to 1,024-element chunks; parties add; one output client receives totals. No comparison, no clipping, no screening. |
| Count binding | same | revealed equality check of the private count against the server-known count; crash on mismatch. |
| Client admission | same | `accept_client_connection` IDs must be selected and unseen; output client must be distinct. |
| Control-plane authentication | `smpc/mp_spdz_party_service.py` | HMAC-SHA256 over method/route/timestamp/request-ID/body; ±300 s clock window; request-ID replay journal (fsync); round-ID reuse journal. |
| Program agreement | `start_round` | every party returns the compiled bytecode SHA-256; mismatch aborts. |
| Abort semantics | `flower_simulation.py` | any missing client, failure, malformed input, party error, MAC failure aborts the round; no plaintext fallback in SMPC mode. |
| MTD | `mtd/controller.py` | secret-derived HMAC schedule when `FL_MTD_SECRET` (≥32 bytes) is set; otherwise deterministic from the public seed; **when MTD is disabled the cohort is the static prefix `clients[:K]`**. |
| Robust detector | `federated/robust_aggregation.py` | plaintext only (median-residual robust z, cosine to median, norm ratio, temporal EMA); explicitly rejected when SMPC is on. |
| Fixed point | `smpc/fixed_point.py` | round-to-nearest, scale 10⁶ in configs; overflow guard for the 2⁶²/max_clients ring range. |
| Local deployment | `smpc/local_demo.py` | all parties, clients, and coordinator share one host and kernel; temporary TLS material. |

* **Tests:** `77 passed` (5.41 s) on 2026-11-19 — re-verified here, matching the earlier report. Distribution: configs 13, security hardening 13, mp_spdz 10, robust aggregation 8, mp_spdz control 6, MTD committee privacy 5, attacks 4, byzantine 4, statistics 3, and 1–2 each in the remaining 7 files.
* **Model:** `CIFAR10CNN` has 2,122,186 floating-point parameters (896 + 18,496 + 2,097,664 + 5,130).

## 4. Existing experimental evidence (re-read, not re-run)

| Evidence | Implementation used | What it shows | What it does **not** show |
|---|---|---|---|
| A: `results/benchmark_lr001` (5 seeds; baseline/MTD/SMPC/hybrid under sign-flip) | **old custom additive SMPC** (field 2⁶¹−1, committees) | multi-seed runs completed for the old prototype | anything about SPDZ2k |
| A: `results/robust_detection_tuned` (5 seeds, CIFAR-10, 5 clients, 40 % sign-flip) | plaintext robust detector | final accuracy 0.629 (robust) vs 0.464 (FedAvg); 2 TP / 0 FP per round | any secure (MPC) defence |
| A: `results/final_audit_report.md` | old prototype, 1 seed, 3 rounds | historical | statistically meaningful conclusions |
| B: `research_output/archive/early_phase_2026-11-18/runtime_optimization` | SPDZ2k sum-only, synthetic vectors, 3 parties | 8–100k elements complete; 100k: 246 s, 401,594 triples, ~43 GB protocol traffic; offline phase dominates | Flower training at that scale |
| B: `research_output/archive/early_phase_2026-11-18/scalability_phase` | SPDZ2k | compile-only scaling to 2.12M; 250k run aborted at 300 s cap; norm-clip prototype (`sfix`, 2-coordinate vectors) | full-model execution, clipping at model scale, malicious-input range safety |
| B: `research_output/archive/early_phase_2026-11-18/final_validation_20261119T194946Z` | SPDZ2k | 77 tests; 2-round, 3-party integrated tiny Flower run with secret MTD and sign-flip, accuracy 0.75 unchanged | poisoning mitigation, baselines, ASR, multiple seeds |
| B: `MPC_BCD_FEASIBILITY.md` | compiler counts | per-coordinate secure comparison + select ≈ 120 triples + 64 random bits per coordinate | runtime |

**Fresh calibration (this audit, 3 local parties, uncontended):** a pure SPDZ2k multiplication circuit ran at ≈3,100 triples/s (40,000 triples: 12.8 s offline, 1.37 GB sent by party 0). Two parties: ≈5,700 triples/s. Larger preprocessing batches (`-b 10000`) did not help. This rate is the binding constraint for any in-MPC defence.

## 5. Component-by-component comparison

| Component | A (`main`) | B (`spdz2k-thesis`) | More complete |
|---|---|---|---|
| Flower FL loop, CIFAR-10, FedAvg | yes | yes (identical lineage) | equal |
| Secure aggregation | custom additive sharing, semi-honest-style | **MP-SPDZ SPDZ2k**, MAC-checked, abort on failure | **B** |
| Control-plane security (auth, replay, round reuse) | committee services | HMAC + journals + bytecode agreement | **B** |
| MTD scheduling | HMAC PRF + committee rotation | HMAC PRF, round-scoped (committees removed) | B (committees obsolete) |
| Plaintext robust detector | yes | yes (same) | equal |
| Attacks | sign-flip, label-flip, random noise | same | equal; both lack backdoor and scaled replacement |
| Multi-seed runner + t-intervals | yes | yes | equal |
| Secure in-MPC defence | none | none (prototype outside production path) | neither |

## 6. Missing functionality (against the thesis declaration)

1. **No privacy-preserving integrity defence in the secure path.** SPDZ2k sums whatever clients submit; the robust detector is disabled in SMPC mode.
2. **Attack coverage:** no scaled model-replacement attack, no backdoor/trigger attack, no attack-success-rate metric, no adaptive attacker that targets a defence or the MPC encoding.
3. **MTD evaluation:** no comparison of static vs deterministic vs secret-derived scheduling; no exposure metrics; no adversary that exploits schedule predictability. When MTD is off, the cohort is the fixed prefix `clients[:K]`, so with a randomly chosen malicious set the malicious share per round depends on a one-off "cohort lottery".
4. **Model scale:** full-model (2.12M) SPDZ2k execution is infeasible on this host (sum-only already ≈246 s per round at 100k). Multi-round, multi-seed secure experiments require a compact model.
5. **Data:** CIFAR-10 only; no non-IID Dirichlet partitioning; no compact dataset/model option.
6. **Measurement:** no per-round MPC timing breakdown or protocol byte counts in FL runs (only an application-level input-byte estimate); no influence metric; no detection/false-positive metrics for any secure mechanism.
7. **Not established (and not to be claimed):** cross-host deployment, dropout recovery, differential privacy, full-model SPDZ2k execution.

## 7. Integration conflicts

| Conflict | Resolution adopted |
|---|---|
| A's uncommitted edits target modules deleted in B (`aggregator_server.py`, `client_sharing.py`, `additive_sharing.py`). | Not merged. They harden a superseded protocol. Preserved byte-for-byte in two backups (Stage-1 backup and `backups/thesis-completion-20261119/main-worktree-uncommitted.patch`). `main`'s worktree is left untouched. |
| A's results/configs use custom-SMPC fields (`committee_size`, `field_modulus`). | Treated as historical evidence of the old prototype; never reported as SPDZ2k results. |
| Both directories share one Git object store and remote. | All new work goes to a new branch `research/thesis-completion` (created from `5c7b497` in worktree B). No push without explicit authorisation. |
| Previous evidence in B is untracked. | Archived (`spdz2k-worktree-untracked-evidence.tgz`, SHA-256 `8a25e8b4…`) before any change; files are left in place and not overwritten. |

## 8. Preservation actions taken before any change

* `/home/ubuntu/gemini/backups/thesis-completion-20261119/`
  * `repository-all-refs.bundle` — `git bundle --all` (verified), SHA-256 `b2ee5385…`
  * `main-worktree-uncommitted.patch` — SHA-256 `049710ac…` (identical to the Stage-1 backup)
  * `spdz2k-worktree-untracked-evidence.tgz` + file list (163 files)
  * `SHA256SUMS`
* Branch `research/thesis-completion` created in worktree B; `main` worktree untouched.

## 9. Recommended final architecture

Keep **Repository B (worktree, new branch) as the single codebase**. Final entry points: `run_experiment.py` (single run) and a new suite runner for the evaluation grid.

```
Flower coordinator ── MTD scheduler (static | deterministic | HMAC secret-derived) ── cohort
   │                                     └─ exposure/predictability logging
   ├─ clients: local training → attack injection (label flip, sign flip, scaled replacement,
   │           noise, backdoor) → encode update Δ = w_local − w_global (fixed point)
   │           → SPDZ2k client input (TLS, authenticated)
   ├─ SPDZ2k parties (3): program selected per configuration
   │     • spdz2k_weighted_sum.mpc   — existing sum-only path (unchanged)
   │     • spdz2k_robust_aggregate.mpc (new) — exact squared L2 norms in MPC,
   │       secure median-based adaptive threshold, secure clipping (secret scale) and/or
   │       norm screening, post-clip verification, weighted sum; reveals only the aggregate
   │       and declared per-round metadata
   └─ output client: decode, aggregate-norm sanity check, update global model, log metrics
Plaintext reference implementations of every secure computation (for numerical validation only).
```

Design constraints derived from the audit:
* per-coordinate secure comparisons (~120 triples each) are not affordable; the defence must use one or two multiplications per coordinate and a constant number of comparisons per client;
* the compact model must keep `(defence cost) × (clients per round)` within ≈1–2·10⁵ triples per round so that multi-seed experiments finish in hours, not days;
* modular wrap-around in Z_2^64 must be analysed: a norm computed modulo 2⁶⁴ can be fooled by out-of-range inputs, so the design and the tests must cover malformed (wrapping) client inputs explicitly.

## 10. Traceability matrix — state at the start of the completion work

| # | Thesis objective | Existing implementation | Existing evidence | Status at audit |
|---|---|---|---|---|
| 1 | Survey/classify attacks (poisoning, inference, malicious clients, update manipulation) | `attacks/` (sign flip, label flip, noise) | unit tests; threat-model doc | partial: no backdoor, no scaled replacement, no inference experiments |
| 2 | Evaluate existing defences and limitations vs adaptive adversaries | plaintext robust detector | A: 5-seed robust-detection results (plaintext) | partial: no adaptive adversary, no secure defence |
| 3 | SMPC to protect updates during aggregation | SPDZ2k sum-only path | 77 tests; vector benchmarks to 100k; tiny integrated run | implemented for confidentiality; integrity of inputs not addressed |
| 4 | MTD as dynamic protection | HMAC secret-derived scheduling | unit tests; tiny run | implemented; not evaluated against predictive adversaries |
| 5 | Hybrid framework (confidentiality, integrity, poisoning resilience, privacy, unpredictability) | SPDZ2k + MTD | tiny smoke run only | incomplete: no secure poisoning defence |
| 6 | Reproducible evaluation (performance, attack/defence effectiveness, overhead) | runner + statistics | old-prototype benchmarks; SPDZ2k vector benchmarks | incomplete: no secure-path attack/defence evaluation |

The final state of this matrix is maintained in `THESIS_OBJECTIVE_TRACEABILITY.md`.
