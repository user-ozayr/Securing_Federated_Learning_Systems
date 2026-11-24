#!/usr/bin/env bash
# Runs in the detached screen session "p3". Waits for F1, installs the staged
# pairing code (outside the repo until then), tests, runs the paired P3 study,
# summarises it, then touches P3_DONE (which releases the queued sum-only rerun).
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
STAGE=/home/ubuntu/staged_p3
BASE=research_output/mtd_defence; OUT=$BASE/experiments
cd "$REPO" || exit 1
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$BASE/p3_chain.log"; }

log "waiting for F1 to finish"
until [ -f "$BASE/F1_DONE" ]; do sleep 60; done
cp "$STAGE/grid.py" "$STAGE/suite.py" src/fl_security/experiments/
cp "$STAGE/test_paired_secrets.py" tests/
cp "$STAGE/p3_paired_summary.py" "$BASE/tools/"
find tests src -name __pycache__ -prune -exec rm -rf {} +
log "pairing code installed"
{ echo "base commit: $(git rev-parse HEAD)"; git status --porcelain; echo
  { git diff --name-only; git ls-files --others --exclude-standard -- src tests run_*.py; } \
    | sort -u | xargs -r sha256sum; } > "$BASE/provenance_p3.txt"
git diff > "$BASE/provenance_p3.diff"

export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"$PY" -m pytest -q tests > "$BASE/test_results_p3.txt" 2>&1; rc=$?; log "pytest rc=$rc"
if [ $rc -ne 0 ]; then log "tests failed; P3 NOT started"; exec bash; fi
log "P3 suite start (80 runs)"
"$PY" run_suite.py --output-root "$OUT" --studies p3 --timeout 3600 2>&1 | tee "$OUT/suite_driver_p3.log"
log "P3 suite rc=${PIPESTATUS[0]}"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver_p3.log" 2>&1; log "analysis rc=$?"
"$PY" $BASE/tools/m1_summary.py "$OUT" p3 > "$OUT/p3_summary.txt" 2>&1; log "summary rc=$?"
"$PY" $BASE/tools/p3_paired_summary.py "$OUT" 2>&1 | tee "$OUT/p3_paired.txt"
touch "$BASE/P3_DONE"; log "P3 done"
exec bash
