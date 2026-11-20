# Setup, reproduction and troubleshooting

## 1. Requirements

* Linux (validated: Ubuntu, aarch64, 3 vCPU, 17 GiB RAM). SPDZ2k party
  processes need POSIX; Windows/macOS can run only the plaintext paths and tests.
* Python 3.11 with `torch`, `torchvision`, `flwr[simulation]==1.38.*`, `ray`,
  `numpy`, `pandas`, `matplotlib`, `PyYAML`, `pytest`.
* MP-SPDZ v0.4.3 with `spdz2k-party.x` built (`make -j2 spdz2k-party.x` in the
  MP-SPDZ tree; `Scripts/setup-ssl.sh` and `Scripts/setup-clients.sh` are used
  automatically by the local deployment).
* Disk: ≈100 MB for Fashion-MNIST, ≈1 MB per instrumented run, ≈60 MB per
  party log set; keep ≥ 3 GB free (benchmarks abort below 2 GB).

## 2. Installation

On the project host the existing interpreter is used unchanged:

```bash
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
export PYTHONPATH=src FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
```

Elsewhere: `python -m pip install -e ".[simulation,dev]"`.

## 3. Reproduction commands

| Purpose | Command |
|---|---|
| Unit/integration tests | `$PY -m pytest -q` |
| Robust program vs exact reference (real SPDZ2k, 13 scenarios, ≈4 min) | `$PY run_mpc_validation.py --output-dir research_output/completion/experiments/mpc_validation` |
| One experiment (plaintext) | `$PY run_experiment.py --config <yaml>` |
| One experiment (SPDZ2k, local parties) | `FL_MTD_SECRET=$($PY -c 'import secrets;print(secrets.token_urlsafe(48))') $PY run_experiment.py --config <yaml> --local-mp-spdz` |
| Full evaluation grid (≈14 h on 3 vCPU, resumable) | `$PY run_suite.py --output-root research_output/completion/experiments` |
| Subset, e.g. the core table only | `$PY run_suite.py --output-root … --studies e1` |
| Aggregate tables and figures | `$PY analyze_suite.py --root research_output/completion/experiments` |
| Recompute the post-run analysis of every completed or aborted run | `$PY analyze_suite.py --root … --reanalyze` |
| Evidence checks (configurations, end-to-end error, imports, log index) | scripts in `research_output/completion/tools/` |
| Fresh-clone validation | `bash research_output/completion/independent_validation.sh` |

The suite skips completed runs and fail-closed aborted runs. Before it repeats an
unfinished run, it moves the earlier attempt to `failed_attempts/<stamp>_auto/`;
nothing is deleted. A running suite keeps the grid it loaded at start-up, so
restart it after changing `grid.py`.
| MTD exposure study (seconds) | `$PY run_mtd_exposure.py --output-dir research_output/completion/experiments/mtd_exposure` |
| SPDZ2k benchmarks (≈1 h, idle host) | `$PY run_mpc_benchmark.py --output-dir research_output/completion/benchmarks` |

Every run directory contains `config.yaml`; re-running `run_experiment.py`
with it reproduces the run (secret-schedule runs need a secret; the stored
SHA-256 commitment identifies the original one without revealing it).
Determinism: client training is seeded per client and round, the robust
aggregation is exact integer arithmetic, and Ray scheduling does not change
which client trains on which data.

## 4. Configuration reference

See `research_output/completion/FINAL_ARCHITECTURE.md` §4 for the YAML schema and
`fl_security.experiments.grid` for every configuration used in the evaluation.
`SecureDefenceConfig.round_spec()` rejects parameter combinations that violate
the 2⁶² bit budget or leave too small a margin for the output check; reduce
`fractional_bits`, `clip_bits`, `weight_bits` or `max_norm` if that happens.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `FL_MPSPDZ_HOME must point to …` | export `FL_MPSPDZ_HOME` to the MP-SPDZ v0.4.3 tree |
| `mtd.schedule 'secret' requires FL_MTD_SECRET` | set a secret of ≥ 32 bytes, or use `deterministic` for reproducible public schedules |
| `SPDZ2k parties compiled different program bytecode` | parties use different MP-SPDZ trees or program files; deploy identical versions |
| `failed to start all SPDZ2k parties` / port errors | leftover processes: `pkill -f '[s]pdz2k-party.x'`; `ray stop --force` |
| `robust specification exceeds the 2^62 bit budget` | lower `max_valid_norm`, `max_norm`, `clip_bits` or `weight_bits` |
| `defence_output_check_passed = 0` in a round | an accepted input wrapped modulo 2⁶⁴ (malformed or colluding clients); the round's update was not applied – investigate the cohort |
| `unexpected data length` (client) | client/program chunk sizes differ; robust mode requires `robust_chunk_size` = `smpc.defence.chunk_size` |
| Run hangs after client training | a client failed before connecting; parties wait until the 600 s round timeout; check `run.log`, the suite's per-run timeout kills the process group |
| Very slow rounds | other CPU load on the host (3 parties + Ray actors share the cores); edaBits enabled (`use_edabits`) – measured 2× slower here |
| Low accuracy in round 1 | expected variance of the first averaged step from a random initialisation; later rounds converge |
| Disk fills up | remove `Programs/Bytecode/fl_spdz_*` leftovers from pre-fix runs; old runs left auxiliary tapes |
| `SPDZ2k round … exceeded its timeout` for large models | rounds longer than 600 s are stopped by the parties (on 3 vCPU, ≈ 100,000 parameters for the robust program); raise `FL_MPSPDZ_ROUND_TIMEOUT` deliberately |
| Code from another checkout is imported | `fl_security` is a namespace package; with an editable install of another tree in the same interpreter, modules missing here resolve there. Put this tree's `src` first on `PYTHONPATH` and run `research_output/completion/tools/import_provenance_check.py` |
| Idle `multiprocessing` workers survive a killed run | local party services are spawned processes; stop leftovers by PID after checking their working directory |
