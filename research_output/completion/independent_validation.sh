#!/usr/bin/env bash
# Independent validation from a fresh clone of the committed branch.
# Uses the existing interpreter (no new environment, no package installation) and
# the public dataset files already on the host. Every output goes to $OUT; the
# suite's evidence directories are only read. Nothing is deleted.
set -u
REPO=/home/ubuntu/gemini/fl-security-research
THESIS=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FRESH=/home/ubuntu/gemini/fresh_validation_clone_$STAMP
OUT=$THESIS/research_output/completion/independent_validation
SUITE_RUNS=$THESIS/research_output/completion/experiments/runs
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

mkdir -p "$OUT/reruns"
if [ -e "$FRESH" ]; then echo "refusing to reuse existing path $FRESH" >&2; exit 2; fi
git clone --quiet --branch research/thesis-completion --single-branch "$REPO" "$FRESH" || exit 3
cd "$FRESH" || exit 4
export PYTHONPATH="$FRESH/src" FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3
export FL_DATA_ROOT="$THESIS/data" FL_MPSPDZ_STARTUP_TIMEOUT=0.5 RAY_DEDUP_LOGS=0
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset FL_MTD_SECRET
{
  echo "fresh clone: $FRESH"
  echo "cloned from: $REPO (branch research/thesis-completion, single branch)"
  echo "commit: $(git rev-parse HEAD)"
  echo "started (UTC): $(now)"
  echo "tracked files modified in clone: $(git status --porcelain --untracked-files=no | wc -l)"
  echo "fl_security imported from: $($PY -c 'import fl_security; print(fl_security.__file__)' 2>&1)"
  echo "interpreter: $PY ($($PY --version 2>&1)); existing environment, nothing installed"
  echo "dataset root: $FL_DATA_ROOT (read only)"
} > "$OUT/clone_info.txt"

$PY -m pytest -v -p no:cacheprovider > "$OUT/pytest_fresh_clone.txt" 2>&1; rc=$?
echo "$(now) pytest (default suite) exit $rc: $(tail -n 1 "$OUT/pytest_fresh_clone.txt")" >> "$OUT/clone_info.txt"

FL_RUN_MPSPDZ_TESTS=1 $PY -m pytest -v -p no:cacheprovider tests/test_mpspdz_integration.py \
  > "$OUT/pytest_mpspdz_fresh_clone.txt" 2>&1; rc=$?
echo "$(now) pytest (real MP-SPDZ integration tests) exit $rc: $(tail -n 1 "$OUT/pytest_mpspdz_fresh_clone.txt")" >> "$OUT/clone_info.txt"

$PY run_mpc_validation.py --output-dir "$OUT/mpc_validation_fresh" > "$OUT/mpc_validation_fresh.log" 2>&1; rc=$?
echo "$(now) SPDZ2k validation scenarios exit $rc" >> "$OUT/clone_info.txt"

# Deterministic re-runs of two suite runs from the clone (same configuration and
# seed; only the output directory differs), compared round by round with the suite.
for run in e1x/e1x__smpc_defence__backdoor__s101 e1/e1__baseline__backdoor__s101; do
  name=$(basename "$run")
  extra=$($PY - "$SUITE_RUNS/$run/config.yaml" "$OUT/reruns/$name" "$OUT/reruns/$name.yaml" <<'PY'
import sys
import yaml
source, output_dir, target = sys.argv[1:4]
with open(source, encoding="utf-8") as handle:
    config = yaml.safe_load(handle)
config["evaluation"]["output_dir"] = output_dir
with open(target, "w", encoding="utf-8") as handle:
    handle.write(yaml.safe_dump(config, sort_keys=True))
print("--local-mp-spdz" if config.get("smpc", {}).get("enabled") else "")
PY
)
  $PY run_experiment.py --config "$OUT/reruns/$name.yaml" $extra > "$OUT/reruns/$name.log" 2>&1; rc=$?
  echo "$(now) rerun $name ${extra:-(plaintext)} exit $rc" >> "$OUT/clone_info.txt"
done

$PY - "$SUITE_RUNS" "$OUT/reruns" > "$OUT/rerun_comparison.txt" 2>&1 <<'PY'
import sys
from pathlib import Path

import pandas as pd

suite_root, rerun_root = Path(sys.argv[1]), Path(sys.argv[2])
NUMERIC = ("global_accuracy", "global_loss", "backdoor_asr", "defence_threshold_norm",
           "defence_aggregate_norm", "defence_accepted_weight")
IDS = ("selected_client_ids", "malicious_client_ids", "defence_accepted_client_ids",
       "defence_rejected_client_ids", "defence_clipped_client_ids")
for study, name in (("e1x", "e1x__smpc_defence__backdoor__s101"), ("e1", "e1__baseline__backdoor__s101")):
    suite_csv = suite_root / study / name / f"{name}_results.csv"
    fresh_csv = rerun_root / name / f"{name}_results.csv"
    if not fresh_csv.exists():
        print(f"{name}: RERUN RESULTS MISSING ({fresh_csv})")
        continue
    a, b = pd.read_csv(suite_csv), pd.read_csv(fresh_csv)
    merged = a.merge(b, on="round", suffixes=("_suite", "_fresh"))
    identical = len(a) == len(b) == len(merged)
    print(f"{name}: rounds suite={len(a)} fresh={len(b)} matched={len(merged)}")
    for column in NUMERIC:
        if f"{column}_suite" not in merged:
            continue
        x, y = merged[f"{column}_suite"], merged[f"{column}_fresh"]
        nan_mismatch = int((x.isna() ^ y.isna()).sum())
        both = x.notna() & y.notna()
        value = float((x[both] - y[both]).abs().max()) if both.any() else 0.0
        identical &= nan_mismatch == 0 and value == 0.0
        print(f"  max |{column}: suite - fresh| = {value}  (NaN mismatches: {nan_mismatch})")
    for column in IDS:
        if f"{column}_suite" not in merged:
            continue
        same = bool((merged[f"{column}_suite"].fillna("").astype(str)
                     == merged[f"{column}_fresh"].fillna("").astype(str)).all())
        identical &= same
        print(f"  {column} identical in every round: {same}")
    print(f"  VERDICT {name}: {'IDENTICAL' if identical else 'DIFFERENT (see values above)'}")
PY
echo "$(now) comparison written to rerun_comparison.txt" >> "$OUT/clone_info.txt"
echo "finished (UTC): $(now)" >> "$OUT/clone_info.txt"
