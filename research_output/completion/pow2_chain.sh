#!/usr/bin/env bash
# Rerun of the 36 E1 sum-only SPDZ2k runs with the power-of-two scale (S = 2^40).
# Runs inside the detached screen session "pow2" (attach: screen -r pow2).
# The change is not committed, so a provenance snapshot (base commit, SHA-256 of
# every modified or new source file, full diff) is written first; every run then
# records git_dirty = true against that snapshot.
set -u
REPO=/home/ubuntu/gemini/fl-security-research-sum-only-correction
THESIS=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
OUT=research_output/completion/experiments_pow2
cd "$REPO" || exit 1
mkdir -p "$OUT"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/chain.log"; }

{
  echo "base commit: $(git rev-parse HEAD)"
  git status --porcelain
  echo; echo "SHA-256 of modified and new source files:"
  { git diff --name-only; git ls-files --others --exclude-standard -- src tests run_*.py; } \
    | sort -u | xargs -r sha256sum
} > "$OUT/provenance.txt"
git diff > "$OUT/provenance.diff"
log "starting on uncommitted changes to $(git rev-parse --short HEAD); provenance in $OUT/provenance.txt"

export PYTHONPATH="$REPO/src" FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3
export FL_DATA_ROOT="$THESIS/data"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
"$PY" -m pytest -q tests > "$OUT/test_results.txt" 2>&1; rc=$?; log "pytest rc=$rc"
if [ $rc -ne 0 ]; then log "tests failed; rerun NOT started"; exec bash; fi
log "suite start (36 runs: smpc_only, smpc_mtd x 6 attacks x 3 seeds)"
"$PY" run_suite.py --output-root "$OUT" --studies e1 --conditions smpc_only smpc_mtd \
  --timeout 3600 2>&1 | tee "$OUT/suite_driver.log"
log "suite finished rc=${PIPESTATUS[0]}"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver.log" 2>&1
log "analysis rc=$?"
touch "$OUT/DONE"; log "rerun done"
exec bash
