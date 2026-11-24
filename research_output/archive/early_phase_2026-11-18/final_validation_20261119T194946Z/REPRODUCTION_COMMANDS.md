# Reproduction commands

Use the thesis checkout on branch `research/spdz2k-thesis`. The configured test interpreter exists in the separate original checkout, but is invoked with the thesis checkout as the current directory and `PYTHONPATH=src`; the original checkout was not modified during validation.

## Full test suite

```bash
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PYTHONPATH=src /home/ubuntu/gemini/fl-security-research/.venv311/bin/python -m pytest -ra tests
```

Observed: exit 0, 77 passed, 0 failed, 5.29 seconds.

## Fresh tiny integrated experiment

The exact modified driver is `run_integrated_mtd_attack_tiny_logged.py`; it runs through `local_demo.run_with_local_mp_spdz`, uses a generated ephemeral `FL_MTD_SECRET`, and writes under `integrated_tiny_logged/`.

```bash
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PYTHONPATH=src /home/ubuntu/gemini/fl-security-research/.venv311/bin/python research_output/final_validation_20261119T194946Z/run_integrated_mtd_attack_tiny_logged.py
```

Requires `/home/ubuntu/gemini/MP-SPDZ-v0.4.3`, local party/client setup tools, and Linux/POSIX. It runs two tiny rounds and typically takes about 35 seconds on the recorded 3-vCPU host. Outputs are isolated in the validation folder.

## Existing vector runtime evidence

The detailed historical run records are copied under `raw_evidence/`. They are evidence from prior same-host runs, not measurements newly repeated in this validation turn. Do not interpret compile-only rows as completed MPC execution.

## Reproducibility caveats

The local Flower integration uses synthetic tensors and a tiny linear model, not CIFAR training. The parties run on one host. Dataset downloads are not required by the synthetic driver. `python -m build --wheel` could not be run because a build frontend is unavailable in the specified environment.
