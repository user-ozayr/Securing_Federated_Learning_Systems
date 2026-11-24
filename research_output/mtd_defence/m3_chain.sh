#!/usr/bin/env bash
# M3 (cohort size bound K = 7 >= 2f + 1), then the seed-103 norm-only baseline
# for M2 (m2b). One study at a time; the source tree is fixed before it starts.
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
BASE=research_output/mtd_defence
OUT=$BASE/experiments
cd "$REPO" || exit 1
log() { echo "$(date -u +%FT%TZ) $*" >> "$BASE/m3_chain.log"; }

{
  echo "base commit: $(git rev-parse HEAD)"
  git status --porcelain
  echo; echo "SHA-256 of modified and new source files:"
  { git diff --name-only; git ls-files --others --exclude-standard -- src tests run_*.py; } \
    | sort -u | xargs -r sha256sum
} > "$BASE/provenance_m3.txt"
git diff > "$BASE/provenance_m3.diff"

export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

"$PY" -m pytest -q tests > "$BASE/test_results_m3.txt" 2>&1; rc=$?; log "pytest rc=$rc"
if [ $rc -ne 0 ]; then log "tests failed; M3 not started"; touch "$BASE/M3_FAILED"; exit 1; fi
for study in m3 m2b; do
  "$PY" run_suite.py --output-root "$OUT" --studies $study --timeout 3600 > "$OUT/suite_driver_$study.log" 2>&1
  log "$study suite rc=$?"
done
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver_m3.log" 2>&1; log "analysis rc=$?"
for study in m3 m2b; do
  "$PY" $BASE/tools/m1_summary.py "$OUT" $study > "$OUT/${study}_summary.txt" 2>&1; log "$study summary rc=$?"
done
touch "$BASE/M3_DONE"
