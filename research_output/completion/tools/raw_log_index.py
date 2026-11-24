"""Write experiments/raw_logs/INDEX.md: where every raw log of the evaluation is.

Raw logs stay next to the artefact they belong to (a run, an archived attempt,
a validation scenario, a benchmark party). The index records their paths and statuses without copying the logs.

Usage: python raw_log_index.py <completion_root>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> None:
    root = Path(sys.argv[1])
    experiments = root / "experiments"
    out_dir = experiments / "raw_logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Raw log index",
        "",
        "Raw logs are stored next to the artefact they belong to; this index lists them.",
        "Paths are relative to `research_output/completion/`.",
        "",
        "Log files (`*.log`) are not tracked by git; the repository's `.gitignore` excludes them.",
        "They remain on the research host, and the SHA-256 of every one of them is recorded in",
        "`final_validation_manifest.json`.",
        "",
        "## Suite drivers and evidence chains",
        "",
    ]
    for path in sorted(experiments.glob("*.log")) + sorted(root.glob("*.log")):
        lines.append(f"* `{relative_path(path, root)}` ({path.stat().st_size:,} bytes)")

    lines += ["", "## Experiment runs (one `run.log` per run)", "",
              "| Study | Run | Status | Commit | Log |", "|---|---|---|---|---|"]
    counts: dict[str, int] = {}
    for metadata_path in sorted(experiments.glob("runs/*/*/run_metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        status = str(metadata.get("status"))
        counts[status] = counts.get(status, 0) + 1
        log = metadata_path.parent / "run.log"
        lines.append(f"| {metadata.get('study')} | {metadata.get('run_id')} | {status} | "
                     f"{str(metadata.get('git_commit', ''))[:7]} | `{relative_path(log, root)}` |")
    lines.insert(lines.index("## Experiment runs (one `run.log` per run)") + 1,
                 "\nStatus counts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ".")

    lines += ["", "## Archived failed attempts (kept unchanged; each was repeated)", "",
              "| Archive | Study | Run | Status at archiving | Log |", "|---|---|---|---|---|"]
    for metadata_path in sorted(experiments.glob("failed_attempts/*/*/*/run_metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        archive = metadata_path.parents[2].name
        log = metadata_path.parent / "run.log"
        lines.append(f"| {archive} | {metadata.get('study')} | {metadata.get('run_id')} | "
                     f"{metadata.get('status')} | `{relative_path(log, root)}` |")
    for reason in sorted(experiments.glob("failed_attempts/*/*/REASON.txt")):
        lines.append(f"\nReason note: `{relative_path(reason, root)}`")

    lines += ["", "## SPDZ2k validation scenarios", ""]
    for path in sorted((experiments / "mpc_validation").rglob("*")):
        if path.is_file() and path.suffix in {".log", ".txt", ".json", ".csv"}:
            lines.append(f"* `{relative_path(path, root)}`")

    benchmark_logs = sorted((root / "benchmarks" / "raw_logs").glob("*"))
    lines += ["", "## Benchmarks", "",
              f"* `benchmarks/raw_logs/`: {len(benchmark_logs)} MP-SPDZ party logs",
              "* `benchmarks_driver.log` (driver output, see above)"]

    validation = root / "independent_validation"
    if validation.exists():
        lines += ["", "## Independent validation (fresh clone)", ""]
        for path in sorted(validation.rglob("*")):
            if path.is_file() and path.suffix in {".log", ".txt"}:
                lines.append(f"* `{relative_path(path, root)}`")
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_dir / 'INDEX.md'} ({sum(counts.values())} runs)")


if __name__ == "__main__":
    main()
