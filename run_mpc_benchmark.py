"""Benchmark SPDZ2k sum-only and robust aggregation across vector sizes.

Run on an otherwise idle host (results include wall-clock times):

    FL_MPSPDZ_HOME=/path/to/MP-SPDZ-v0.4.3 python run_mpc_benchmark.py \
        --output-dir research_output/completion/benchmarks

Completed cases are skipped on restart (benchmark_results.jsonl).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fl_security.smpc.benchmark import BenchmarkCase, run_benchmarks


def default_cases() -> list[BenchmarkCase]:
    cases = []
    for dimension in (1_000, 2_202, 10_000):
        for repeat in range(3):
            cases.append(BenchmarkCase("weighted_sum", dimension, repeat=repeat))
            cases.append(BenchmarkCase("robust_aggregate", dimension, repeat=repeat))
    for dimension in (2_202, 10_000):
        for repeat in range(2):
            cases.append(BenchmarkCase("robust_aggregate", dimension, mode="clip",
                                       threshold="static", repeat=repeat))
            cases.append(BenchmarkCase("robust_aggregate", dimension, mode="screen",
                                       threshold="adaptive", repeat=repeat))
    for dimension in (50_000, 100_000):
        cases.append(BenchmarkCase("weighted_sum", dimension))
        cases.append(BenchmarkCase("robust_aggregate", dimension))
    cases.append(BenchmarkCase("weighted_sum", 250_000))
    for repeat in range(2):
        cases.append(BenchmarkCase("weighted_sum", 2_202, parties=2, repeat=repeat))
        cases.append(BenchmarkCase("robust_aggregate", 2_202, parties=2, repeat=repeat))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cap-seconds", type=float, default=1800.0)
    parser.add_argument("--max-dimension", type=int, default=None)
    args = parser.parse_args()
    cases = default_cases()
    if args.max_dimension:
        cases = [case for case in cases if case.dimension <= args.max_dimension]
    run_benchmarks(cases, Path(args.output_dir), args.cap_seconds)


if __name__ == "__main__":
    main()
