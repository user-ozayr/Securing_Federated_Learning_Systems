# Reproduction commands

* **Host and repository:** `ubuntu@<research host>`, repository
  `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`, branch
  `research/thesis-completion`.
* **Final code commit:** `e4c090a`.
* **Per-run records** in `runs/<study>/<run_id>/run_metadata.json`:
  * the commit the run executed (`git_commit`; `git_dirty` is false for all 228
    runs);
  * the SHA-256 of its configuration (`config_sha256`);
  * for secret-schedule runs, the SHA-256 commitment of the MTD secret.

```bash
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python   # existing environment
export PYTHONPATH=src FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
```

Keep `src` of this tree first on `PYTHONPATH`. The interpreter also carries an
editable install of the other worktree, and `fl_security` is a namespace package
(see `tools/import_provenance_check.py`).

## Tests

```bash
$PY -m pytest -q                                   # 131 passed, 1 skipped (opt-in) at e4c090a
FL_RUN_MPSPDZ_TESTS=1 $PY -m pytest -q tests/test_mpspdz_integration.py   # real 3-party SPDZ2k
```

## SPDZ2k validation of the robust program (13 scenarios, about 4 min)

```bash
$PY run_mpc_validation.py --output-dir research_output/completion/experiments/mpc_validation
```

## Evaluation grid (studies e1, e1x, e2, e3, e4, e5; 228 runs; about 14 h on 3 vCPU)

```bash
$PY run_suite.py --output-root research_output/completion/experiments --timeout 3600
$PY run_suite.py --output-root research_output/completion/experiments --studies e1   # core table only
```

The suite skips completed runs and fail-closed aborted runs. Since `e4c090a`, it
moves an unfinished attempt to `failed_attempts/<stamp>_auto/` before repeating
it. A running suite keeps the grid it loaded at start-up, so restart it after
changing `grid.py`.

### What was executed for this evidence (in order)

1. **Pass 1:** all 228 runs (`suite_driver.log`), leaving 21 unfinished attempts.
2. **`followup_chain.sh`:**
   * copied the 21 unfinished attempts to `failed_attempts/20261120T122906Z/`;
   * repeated them (pass 2, `suite_driver_pass2.log`);
   * ran the isolated benchmarks (`../benchmarks_driver.log`).

   The `rc=` values in `followup_chain.log` are not exit codes; see
   `FINAL_VALIDATION_REPORT.md` §10.
3. **`final_chain.sh`:**
   * moved the attempt aborted by a TLS reset to
     `failed_attempts/20261120T154646Z_infra/` and repeated it (pass 3,
     `suite_driver_pass3.log`);
   * ran the independent validation (`../independent_validation.sh`);
   * wrote the test report;
   * re-analysed all runs.
4. **After the tooling fix `e4c090a`** (snapshot of the earlier derived files in
   the backup directory):

   ```bash
   C=research_output/completion
   $PY analyze_suite.py --root $C/experiments --reanalyze --benchmarks $C/benchmarks
   $PY $C/tools/move_stale_attempt_files.py $C/experiments
   $PY $C/tools/e2e_reference_summary.py $C/experiments
   $PY $C/tools/verify_run_configs.py $C/experiments > $C/experiments/summaries/config_consistency_check.txt
   bash $C/final_tests.sh                     # test_results.txt + supplementary fresh clone of e4c090a
   $PY $C/tools/raw_log_index.py $C
   ```

5. **Last step: SHA-256 manifest of the completion directory.**

   ```bash
   $PY analyze_suite.py --root $C/experiments --manifest $C
   ```

### Repeating a single run

```bash
$PY run_experiment.py --config research_output/completion/experiments/configs/e1/e1__baseline__backdoor__s101.yaml
FL_MTD_SECRET="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  $PY run_experiment.py --local-mp-spdz \
  --config research_output/completion/experiments/configs/e1/e1__smpc_defence_mtd__backdoor__s101.yaml
```

Runs with `mtd.schedule: secret` use a fresh secret. They reproduce the
distribution of schedules, not the identical cohorts, because the original
secret exists only as its SHA-256 commitment. All other runs are deterministic:
clients train with per-client seeds and the secure aggregation is exact integer
arithmetic. Two of them were reproduced identically from a fresh clone
(`../independent_validation/rerun_comparison.txt`).

## Independent validation (fresh clone, existing interpreter)

```bash
bash research_output/completion/independent_validation.sh   # tests, 13 scenarios, two deterministic re-runs
```

## MTD exposure study

```bash
$PY run_mtd_exposure.py --output-dir research_output/completion/experiments/mtd_exposure --trials 200 --rounds 10 100
```

## Update leakage (E6, about 10 + 30 min on 3 vCPU)

```bash
FL_DATA_ROOT=<tree with data/FashionMNIST> research_output/completion/experiments/leakage/calibrate.sh
FL_DATA_ROOT=<tree with data/FashionMNIST> research_output/completion/experiments/leakage/evaluate.sh
# merge and figures only (after the shards):
$PY run_leakage_study.py --output-dir research_output/completion/experiments/leakage/evaluation --num-shards 3 --merge
$PY research_output/completion/tools/leakage_figures.py research_output/completion/experiments/leakage/evaluation
```

The trials are deterministic given the seed (cohorts, batches and attack
initialisation are seeded); runtimes vary.

## SPDZ2k benchmarks (run with no other experiment on the host)

```bash
$PY run_mpc_benchmark.py --output-dir research_output/completion/benchmarks --cap-seconds 1800
```

## Calibration runs (used to choose parameters)

```bash
$PY run_experiment.py --config research_output/completion/experiments/calibration/calib_plain.yaml
$PY run_experiment.py --local-mp-spdz --config research_output/completion/experiments/calibration/calib_hybrid.yaml
```
