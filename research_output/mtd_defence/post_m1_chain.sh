#!/usr/bin/env bash
# After M1, one step at a time: tests, M1 re-analysis, SPDZ2k validation of the
# extended program (20 scenarios), direction-screen cost benchmark, M2 study.
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
BASE=research_output/mtd_defence
OUT=$BASE/experiments
cd "$REPO" || exit 1
log() { echo "$(date -u +%FT%TZ) $*" >> "$BASE/post_m1_chain.log"; }

{
  echo "base commit: $(git rev-parse HEAD)"
  git status --porcelain
  echo; echo "SHA-256 of modified and new source files:"
  { git diff --name-only; git ls-files --others --exclude-standard -- src tests run_*.py; } \
    | sort -u | xargs -r sha256sum
} > "$BASE/provenance_post_m1.txt"
git diff > "$BASE/provenance_post_m1.diff"

export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

"$PY" -m pytest -q > "$BASE/test_results_post_m1.txt" 2>&1; log "pytest rc=$?"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver_post.log" 2>&1; log "M1 re-analysis rc=$?"
"$PY" $BASE/tools/m1_summary.py "$OUT" m1 > "$OUT/m1_summary.txt" 2>&1; log "M1 summary rc=$?"
"$PY" run_mpc_validation.py --output-dir $BASE/mpc_validation > $BASE/mpc_validation.log 2>&1; log "SPDZ2k validation rc=$?"
"$PY" $BASE/tools/direction_benchmark.py $BASE/direction_benchmark > $BASE/direction_benchmark.log 2>&1; log "benchmark rc=$?"
"$PY" run_suite.py --output-root "$OUT" --studies m2 --timeout 3600 > "$OUT/suite_driver_m2.log" 2>&1; log "M2 suite rc=$?"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver_m2.log" 2>&1; log "M2 analysis rc=$?"
"$PY" $BASE/tools/m1_summary.py "$OUT" m2 > "$OUT/m2_summary.txt" 2>&1; log "M2 summary rc=$?"
touch "$BASE/POST_M1_DONE"
