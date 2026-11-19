"""Aggregate completed experiment runs into tables and figures.

    python analyze_suite.py --root research_output/completion/experiments \
        [--benchmarks research_output/completion/benchmarks] \
        [--manifest research_output/completion]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from fl_security.experiments.report import benchmark_report, build_manifest, build_reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--benchmarks", default=None)
    parser.add_argument("--manifest", default=None, help="write a SHA-256 manifest of this directory")
    args = parser.parse_args()
    print(json.dumps(build_reports(Path(args.root)), indent=2))
    if args.benchmarks:
        summary = benchmark_report(Path(args.benchmarks))
        print("benchmark rows:", 0 if summary is None else len(summary))
    if args.manifest:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        print(json.dumps(build_manifest(Path(args.manifest), extra={"git_head": commit}), indent=2))


if __name__ == "__main__":
    main()
