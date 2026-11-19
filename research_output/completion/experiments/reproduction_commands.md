# Reproduction commands

Host: `ubuntu@<research host>`; repository
`/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`, branch
`research/thesis-completion`. All runs used the commit recorded in each
`runs/<study>/<run_id>/run_metadata.json` (`git_commit`, `git_dirty`).

```bash
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
export PYTHONPATH=src FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
```

## Tests

```bash
$PY -m pytest -q                                           # 120+ tests, no MPC processes
FL_RUN_MPSPDZ_TESTS=1 $PY -m pytest -q tests/test_mpspdz_integration.py   # real 3-party SPDZ2k
```

## SPDZ2k validation of the robust program (13 scenarios)

```bash
$PY run_mpc_validation.py --output-dir research_output/completion/experiments/mpc_validation
```

## Evaluation grid (studies e1, e1x, e2, e3, e4, e5; 228 runs)

```bash
$PY run_suite.py --output-root research_output/completion/experiments --timeout 3600
$PY run_suite.py --output-root research_output/completion/experiments --studies e1   # core table only
$PY analyze_suite.py --root research_output/completion/experiments \
    --benchmarks research_output/completion/benchmarks --manifest research_output/completion
```

A single run can be repeated from its stored configuration:

```bash
$PY run_experiment.py --config research_output/completion/experiments/configs/e1/e1__baseline__backdoor__s101.yaml
FL_MTD_SECRET="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  $PY run_experiment.py --local-mp-spdz \
  --config research_output/completion/experiments/configs/e1/e1__smpc_defence_mtd__backdoor__s101.yaml
```

Runs with `mtd.schedule: secret` use a fresh secret; they reproduce the
distribution of schedules, not the identical cohorts (the original secret is
represented only by its SHA-256 commitment). All other runs are deterministic
(per-client seeded training, exact integer secure aggregation).

## MTD exposure study

```bash
$PY run_mtd_exposure.py --output-dir research_output/completion/experiments/mtd_exposure --trials 200 --rounds 10 100
```

## SPDZ2k benchmarks (run on an idle host)

```bash
$PY run_mpc_benchmark.py --output-dir research_output/completion/benchmarks --cap-seconds 1800
```

## Calibration runs (used to choose parameters)

```bash
$PY run_experiment.py --config research_output/completion/experiments/calibration/calib_plain.yaml
$PY run_experiment.py --local-mp-spdz --config research_output/completion/experiments/calibration/calib_hybrid.yaml
```
