# Reproducibility guide

## Tested environment

- Host: Ubuntu 26.04 LTS, Linux `7.0.0-1009-oracle`, aarch64, Oracle Neoverse-N1, 3 vCPUs.
- Python: 3.11.18. The active environment was `/home/ubuntu/gemini/fl-security-research/.venv311`; because it is an editable environment associated with the original checkout, all test commands explicitly set `PYTHONPATH` to the thesis worktree `src/`. The original checkout's source was not imported.
- Versions: PyTorch 2.15.0+cu132, Flower 1.38.0, pytest 9.2.0, setuptools 84.2.1, wheel 0.46.3. `pip` and the `build` front-end were unavailable in that environment.
- MP-SPDZ: v0.4.3, Git revision `26a605368e40fed3a7e9cee78c9a3f4390b85eb5`; C++ build uses clang++, native ARM flags. The checked-in party service compiles with `-R 64 -M`; execution uses `spdz2k-party.x -p <id> -N <count> -ip <hosts> -e <program>`. Runtime logs reported SPDZ2k security parameter 64 and statistical security parameter 40; retain the raw values and consult v0.4.3 parameter definitions before translating them into a probability claim.
- Direct profile: 3 parties, 3 clients, chunk size 1,024, ring `2^64`, fixed-point scale 100,000, counts [1,2,3], deterministic synthetic tensor values. Watchdog 300 s and 6 GiB per process; host memory/disk guards were also enabled.

## Tests and checks

From `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`:

```bash
PYTHONPATH="$PWD/src" /home/ubuntu/gemini/fl-security-research/.venv311/bin/python -m pytest -q
PYTHONPATH="$PWD/src" /home/ubuntu/gemini/fl-security-research/.venv311/bin/python -m compileall -q src tests
git diff --check
```

Wheel build used the installed PEP 517 backend directly, writing outside the checkout:

```bash
mkdir -p /tmp/thesis-wheel
/home/ubuntu/gemini/fl-security-research/.venv311/bin/python -c 'from setuptools.build_meta import build_wheel; import sys; print(build_wheel(sys.argv[1]))' /tmp/thesis-wheel
```

The produced wheel was `fl_security-0.3.0-py3-none-any.whl`; archive inspection confirmed it includes `spdz2k_weighted_sum.mpc` and excludes removed additive-sharing modules. Latest full-suite result after engineering regression additions: 77 passed, two Typer/Click deprecation warnings. The standard `python -m build --wheel` command is unavailable because the `build` module is not installed.

## Reproducing direct profiling

The exact non-secret profile harness used for the recorded direct runs is preserved at `RAW_EXPERIMENT_RESULTS/profile_mpc_run.py`. It provisions temporary local credentials/SSL material through `local_demo`, launches one MP-SPDZ service per party, sends deterministic inputs through the production client helper, verifies output against a Python reference, records phase/profile samples, and aborts after 300 s or a 6 GiB party RSS guard. It writes results below `research_output/runtime_optimization/` using repository-specific absolute paths; adapt only those paths when running elsewhere. It requires the pinned MP-SPDZ tree and the Python 3.11 environment above.

From the thesis worktree, the previously successful parameter sizes can be rerun serially with: `PYTHONPATH="$PWD/src" /home/ubuntu/gemini/fl-security-research/.venv311/bin/python research_output/final_thesis_package/RAW_EXPERIMENT_RESULTS/profile_mpc_run.py 1000 on` (replace `1000` only with 8, 10000, 50000, or 100000). **Do not run 250k, 500k or full shape under the documented 300 s policy:** 100k already took 246 s and 250k hit the cap. Do not run benchmarks concurrently. The saved `-M` off/on A/B is an archival comparison; the copied harness is not a valid `-M off` reproducer because the production service now enables `-M` by default.

The actual Flower launcher is `python run_experiment.py --config <yaml> --local-mp-spdz`. `FL_MPSPDZ_HOME` must point to the MP-SPDZ v0.4.3 tree. Local mode provisions and removes its temporary service, SSL, and client material. For deployment, party configuration and client credentials must be provisioned securely; environment variable names include `FL_MPSPDZ_PARTIES_JSON`, `FL_MPSPDZ_CLIENT_PORT_BASE`, `FL_MPSPDZ_CLIENT_CREDENTIALS_DIR`, and `FL_MPSPDZ_HOME`. MTD optionally reads `FL_MTD_SECRET` (minimum 32 bytes). This guide intentionally contains no secret values.

## Validation expectations and limitations

A successful direct probe prints `status=PASS`, `max_abs_error=0.0`, counts [1,2,3], and produces party logs with preprocessing/online timing, triple use and global data sent. The 10k initial attempt is expected to remain recorded as a failed output-framing run; corrected runs use one full-array receive. The smoke Flower log is a synthetic 8-parameter one-round run, not CNN training. All profile tests are same-host; no cross-host performance or deployment security is implied.
