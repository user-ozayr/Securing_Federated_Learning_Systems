# Implementation Report — Completion of the Hybrid SPDZ2k + MTD Framework

Branch `research/thesis-completion` in worktree
`/home/ubuntu/gemini/fl-security-research-spdz2k-thesis` (base `5c7b497`).
Python environment: the existing `/home/ubuntu/gemini/fl-security-research/.venv311`
(no new environment was created; no packages were installed).

## 1. Starting point and integration decision

The two "repositories" are two worktrees of one Git repository
(`INITIAL_REPOSITORY_AUDIT.md`). The SPDZ2k worktree already contained all of
`main`'s committed functionality except the old custom additive-sharing SMPC,
which it had replaced. The completion work therefore continues on the SPDZ2k
line; `main`'s uncommitted edits to the superseded custom SMPC were preserved as
patches and not merged. The sum-only SPDZ2k path, the control-plane security
features and the plaintext detector are kept and remain covered by the original
77 tests, which still pass.

## 2. The central contribution: an integrity defence inside SPDZ2k

Design constraints were measured first (`docs/secure_robust_aggregation.md` §2):
≈3,100 triples/s for three parties on the host, one triple per client input and
per output value, ≈126 triples plus ≈63 random bits per comparison. This rules
out per-coordinate secure comparisons and `sfix` multiplications at model scale,
and fixed the shape of the solution:

* integer-only arithmetic in Z_2^64 – no truncation inside MPC; scaling is
  deferred to public decoding;
* one dot product per client for the squared norm, one secret scalar–vector
  product per accepted client for clipping;
* a constant number of comparisons per client (validity 2, screening 1, clipping
  `g`), and `K(K−1)/2 + 2` for the secure lower-median threshold;
* decisions on the **visible contribution** (`w²R`, `C²w²R`) instead of the raw
  input norm, because inputs are arbitrary ring elements: an analysis during the
  implementation showed that an odd public weight (and, similarly, an
  invertible clip coefficient) lets a client choose its visible contribution
  freely while its raw squared norm is pseudo-random – a brute-forceable bypass of
  a naive check. Squaring commutes with scalar factors in the ring, so checking
  `c²·S` checks the contribution that is actually summed;
* an explicit bit budget (all compared products < 2⁶² for valid inputs) and a
  plaintext output-norm check with a validated margin, which together bound
  single-client encoding attacks; colluding encoding attacks remain a documented
  limitation (closing it requires per-coordinate range proofs).

Comparison semantics were taken from the MP-SPDZ compiler source
(`sint.__lt__` = `LessThanZero(a−b, bit_length+1)` = sign of the 64-bit
difference); the reference implementation emulates exactly this, including for
out-of-range values.

## 3. File-level change record

| File | Change |
|---|---|
| `src/fl_security/smpc/programs/spdz2k_robust_aggregate.mpc` | **new** robust program (norms, median, screen, clip, aggregate, header) |
| `src/fl_security/smpc/robust.py` | **new** config/validation, exact reference, encoding, decoding, output check, `apply_delta` |
| `src/fl_security/smpc/validation.py`, `run_mpc_validation.py` | **new** 13-scenario SPDZ2k validation incl. malformed and colluding inputs |
| `src/fl_security/smpc/benchmark.py`, `run_mpc_benchmark.py` | **new** controlled SPDZ2k benchmarks with watchdog and compiler counts |
| `src/fl_security/smpc/mp_spdz.py` | robust start payload; concurrent party start; `submit_client_delta`, `submit_wire_values`, `receive_robust_result`; `finish_round` returns MP-SPDZ statistics |
| `src/fl_security/smpc/mp_spdz_party_service.py` | robust program identity with strict payload validation; source-header argument injection; parse/report MP-SPDZ measurements; remove all round tapes on cleanup (bug fix: auxiliary tapes leaked); configurable startup window |
| `src/fl_security/smpc/local_demo.py` | `local_spdz2k_environment()` context manager (reused by validation/benchmarks); startup window from `FL_MPSPDZ_STARTUP_TIMEOUT` |
| `src/fl_security/federated/flower_simulation.py` | dataset/model options, robust SPDZ2k path, plaintext reference defence, adaptive-attacker threshold publication, predictive adversaries, ASR, timing and MPC statistics, defence/detection columns, evaluation-only instrumentation |
| `src/fl_security/federated/{dataset,model,training}.py` | Fashion-MNIST/MNIST, Dirichlet partitions, `CompactCNN` (2,202 params), `build_model`, batch-transform hook |
| `src/fl_security/attacks/backdoor.py` | **new** BadNets trigger, poisoning, ASR |
| `src/fl_security/attacks/byzantine.py` | scaled replacement, backdoor, adaptive backdoor, stratified/predictive placement, per-round assignment (existing behaviour unchanged) |
| `src/fl_security/mtd/controller.py` | explicit `schedule: static/deterministic/secret` with validation (legacy behaviour unchanged) |
| `src/fl_security/mtd/exposure.py`, `mtd/simulation.py`, `run_mtd_exposure.py` | **new** adversary models, exposure metrics, Monte-Carlo study |
| `src/fl_security/experiments/*`, `run_suite.py`, `analyze_suite.py` | **new**: the experiment grid; a resumable runner (process isolation, timeouts, secret commitments, unfinished attempts moved aside before a repeat); post-run analysis restricted to the cohort each run recorded; reports, including the attack/defence matrix with seed-matched, named references |
| `tests/test_*` (9 new files) | 55 new tests: 54 run by default, plus 1 opt-in real MP-SPDZ integration test (`FL_RUN_MPSPDZ_TESTS=1`). The 77 existing tests are unmodified and pass. Total: 131 passed, 1 skipped by default |
| `research_output/completion/tools/*` | evidence checks: configuration consistency, end-to-end reference summary, import provenance, raw-log index, and moving stale attempt files |
| `.gitignore` | `experiments/` anchored to the root (it silently ignored the new package and the evidence directory) |
| `docs/*` | new: `secure_robust_aggregation.md`, `mtd_scheduling.md`, `reproduction.md`; updated: architecture, threat model, methodology, limitations, SPDZ2k implementation; superseded notices on the two earlier "no clipping" decision documents |

## 4. Problems found and resolved during the work

| Problem | Evidence | Resolution |
|---|---|---|
| `compile.py -o` still appends all arguments to bytecode names (≈200+ characters, grows with cohort size) | compile output | validated arguments injected as a source header; short names; hash still binds parameters |
| Cleanup left auxiliary bytecode tapes (76 leftover files) | `Programs/Bytecode` listing | cleanup removes `<name>-*.bc` |
| Weight-inverse bypass of naive norm checks | analysis + validation scenario `inverse_weight_trick` | decisions on the visible contribution |
| A coordinate of 2⁴⁰ wraps to a zero square | validation preview | documented as a wrap case; covered by the output check (`wrap_large_coordinate`) |
| Serial party start (≈9.7 s per round) | calibration | concurrent start + 0.5 s startup window in the local harness: ≈4.2 s |
| edaBits (MP-SPDZ suggestion) | A/B calibration: 64–67 s vs 31–34 s per round, 5.6–6.0 GB vs 4.0 GB | kept as an option, disabled by default (negative result) |
| `label_sorted` ordering | review | original `np.argsort` call kept to preserve earlier partitions |
| E5 configuration violated the output-check margin (3-bit sample weights, `max_norm` 16) | margin arithmetic | E5 uses `clip_bits = 6`, 2-bit weights; runs re-executed after the fix (`68f8970`) |
| Per-round metrics lost when a secure run aborted | `e1__smpc_only__sign_flip__s101`: model diverged under sum-only SPDZ2k, clients' fixed-point guard refused to encode it in round 4, round aborted fail-closed | partial results + `*_abort.json` saved; runs classified `aborted` (`f75eb7b`); aborted runs re-executed with the fix |
| Absolute reference error misleading for diverged models (4.2·10⁶ at ‖w‖∞ ≈ 10¹⁴) | FedAvg sign-flip run | relative error and model magnitude added; relative error 2.8·10⁻⁸ |
| Screen-only grid configuration violated the output-check margin (bound ρ·τ_max = 32 needs 256×, `g = 8` gives 128×) | all 12 `e1x__smpc_screen__*` runs rejected at round 1 by `round_spec` (the validation worked as designed) | `clip_bits = 6` for screen-only (`99366f7`); a whole-grid validation of all 94 defence configurations now passes. Process lesson: validate every generated configuration before launching a long suite |
| A running suite process keeps the grid it loaded at start-up | the archived pass-1 E5 and screen-only attempts carry the pre-fix parameters although they ran under the fixed commit (`git_commit` records the code each run executed) | those runs failed validation and were repeated by a new suite process; every one of the 228 stored configurations equals the final grid byte for byte (`tools/verify_run_configs.py`). Process lesson: restart the suite after changing `grid.py` |
| The post-run analysis mixed per-client files of an earlier attempt into a repeated run | two aborted sum-only SPDZ2k runs with a secret schedule showed 6–8 "participants" per round and relative errors up to 1.1. The first pass had archived failed attempts by copying them, and the repeats reused the directories | `e4c090a`: the analysis uses only the cohort each run recorded (ignored entries are counted, inconsistent rounds flagged), and the suite moves unfinished attempts aside before repeating them; all runs were re-analysed. Only the two affected runs changed (15 stale entries ignored; their error is now 2–3·10⁻⁸ relative). A snapshot of the earlier derived files is in the backup directory |
| Stale `*_abort.json` of a rejected first attempt left in 15 completed run directories | file older than the repeat's start time | moved next to its byte-identical archived copy; log in `experiments/failed_attempts/STALE_FILES_MOVED.txt` |
| The matrix counted the low ASR of a ruined model as partial mitigation | MTD-only and SMPC+MTD under the backdoor were labelled "partially mitigated" at accuracies of 0.32 and 0.41 | `e4c090a`: a halved ASR counts only if accuracy is not worse than the undefended baseline; `model_destroyed` column; references are seed-matched and named |
| Four idle party-service processes orphaned by an early calibration run | found before the final validation (no CPU use, about 1.8 GB RSS) | stopped. The return codes printed by the follow-up chain were the status of `date` (shell `$?` after command substitution); later scripts capture exit codes directly |

## 5. Validation performed before the evaluation

* 131 unit and integration tests pass, and so does the opt-in real MP-SPDZ
  integration test (`test_results.txt`). The same tests pass in fresh clones of
  `99366f7` and `e4c090a` (`independent_validation/`).
* Real SPDZ2k (3 parties): 13 scenarios, all revealed values bit-identical to the
  reference; output check behaves as analysed.
* Full pipeline smoke runs (Flower + SPDZ2k robust + secret MTD + backdoor):
  attackers rejected inside MPC; per-round MP-SPDZ statistics recorded.
* Every instrumented FL run compares the applied update with the reference
  recomputed from the clients' actual updates (`round_analysis.csv`).

## 6. Commits

| Commit | Content |
|---|---|
| `071fbbc` | implementation, tests, audit, MPC validation evidence |
| `68f8970` | documentation, report tooling, benchmark harness, MTD exposure study, E5 margin fix |
| `f75eb7b` | fail-closed abort keeps completed rounds; relative reference error; re-analysis |
| `99366f7` | screen-only grid configuration fixed (output-check margin) |
| `e4c090a` | analysis restricted to the recorded cohort; unfinished attempts moved aside before a repeat; `--reanalyze` includes aborted runs; sharper matrix verdicts |
| later commits | documentation, evaluation evidence and final reports (see `git log`) |

Experiment code paths are identical across `071fbbc`, `68f8970`, `f75eb7b` and
`99366f7` for runs that complete. `f75eb7b` changes only what is saved when a run
aborts; `99366f7` changes only the screen-only grid parameters; `e4c090a`
changes only the post-run tooling. Each run records in `run_metadata.json` the
commit it executed (`git_dirty` is false for all 228 runs).
