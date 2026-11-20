"""Check that every stored run configuration equals what the final grid generates.

The suite process builds each run's configuration from the grid module it
loaded at start-up, while the run itself executes the code on disk (recorded as
``git_commit``). This check regenerates every configuration from the current
grid exactly as ``suite.run_one`` does and compares it, byte for byte, with the
stored ``config.yaml`` of the run and with its recorded ``config_sha256``.

Usage (repository root): PYTHONPATH=src python verify_run_configs.py <experiments_root>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

from fl_security.experiments.grid import all_runs


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    specs = all_runs(None)
    missing, text_mismatch, hash_mismatch = [], [], []
    for spec in specs:
        run_dir = root / "runs" / spec.study / spec.run_id
        config = json.loads(json.dumps(spec.config))
        config["evaluation"]["output_dir"] = str(run_dir)
        text = yaml.safe_dump(config, sort_keys=True)
        stored_path = run_dir / "config.yaml"
        if not stored_path.exists():
            missing.append(spec.run_id)
            continue
        if stored_path.read_text(encoding="utf-8") != text:
            text_mismatch.append(spec.run_id)
        metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        if metadata.get("config_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            hash_mismatch.append(spec.run_id)
    stored_runs = len(list(root.glob("runs/*/*/config.yaml")))
    print(f"grid specifications: {len(specs)}; stored runs: {stored_runs}")
    print(f"missing runs: {len(missing)} {missing[:10]}")
    print(f"config.yaml differing from the final grid: {len(text_mismatch)} {text_mismatch[:10]}")
    print(f"config_sha256 differing from the final grid: {len(hash_mismatch)} {hash_mismatch[:10]}")
    ok = not (missing or text_mismatch or hash_mismatch) and stored_runs == len(specs)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
