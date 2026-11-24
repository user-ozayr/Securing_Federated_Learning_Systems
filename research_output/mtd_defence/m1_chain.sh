#!/usr/bin/env bash
# M1: moving-target direction screen, plaintext reference of the algorithm.
# 70 runs, one at a time (run_suite executes sequentially), then the analysis.
# The branch is uncommitted, so a provenance snapshot (diff + file hashes) is
# written first; every run's metadata records git_dirty = true.
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
OUT=research_output/mtd_defence/experiments
cd "$REPO" || exit 1
mkdir -p "$OUT"
log() { echo "$(date -u +%FT%TZ) $*" >> "$OUT/chain.log"; }

{
  echo "base commit: $(git rev-parse HEAD)"
  git status --porcelain
  echo; echo "SHA-256 of modified and new source files:"
  { git diff --name-only; git ls-files --others --exclude-standard -- src tests run_*.py; } \
    | sort -u | xargs -r sha256sum
} > "$OUT/provenance.txt"
git diff > "$OUT/provenance.diff"

export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
log "pytest"
"$PY" -m pytest -q > "$OUT/test_results.txt" 2>&1; log "pytest rc=$?"
log "suite start"
"$PY" run_suite.py --output-root "$OUT" --studies m1 --timeout 3600 > "$OUT/suite_driver.log" 2>&1
log "suite rc=$?"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver.log" 2>&1
log "analysis rc=$?"
touch "$OUT/DONE"
