"""Run or resume the completion experiment suite.

Example:

    FL_MPSPDZ_HOME=/path/to/MP-SPDZ-v0.4.3 python run_suite.py \
        --output-root research_output/completion/experiments --studies e1 e3 e2

Completed runs are skipped when the suite resumes. See
fl_security.experiments.grid for the configurations, attacks, and seeds.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fl_security.experiments.grid import STUDIES
from fl_security.experiments.suite import run_suite


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the experiment suite")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--studies", nargs="*", choices=sorted(STUDIES), default=None)
    parser.add_argument("--timeout", type=int, default=3600, help="per-run timeout in seconds")
    parser.add_argument("--max-runs", type=int, default=None)
    parser.add_argument("--mpc", choices=["only", "none"], default=None,
                        help="restrict to SPDZ2k runs or to plaintext runs")
    parser.add_argument("--conditions", nargs="*", default=None,
                        help="restrict to these configuration names (e.g. smpc_only smpc_mtd)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    only_mpc = None if args.mpc is None else args.mpc == "only"
    run_suite(Path(args.output_root), args.studies, args.timeout, args.max_runs, only_mpc,
              args.dry_run, args.conditions)


if __name__ == "__main__":
    main()
