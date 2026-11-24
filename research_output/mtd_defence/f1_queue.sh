#!/usr/bin/env bash
# Runs inside the detached screen session "fl". Waits for the F1 pilot, then runs
# the full F1 study only if the pilot succeeded within 90 minutes; afterwards
# analysis and summary, then F1_DONE (which releases the queued sum-only rerun).
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
BASE=research_output/mtd_defence; OUT=$BASE/experiments
cd "$REPO" || exit 1
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$BASE/f1_chain.log"; }
export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
log "waiting for the F1 pilot"
until [ -f "$BASE/F1_PILOT_DONE" ]; do sleep 60; done
read -r rcpart secpart < "$BASE/f1_pilot_result.txt"
rc=${rcpart#rc=}; secs=${secpart#seconds=}
log "pilot rc=$rc seconds=$secs"
if [ "$rc" != 0 ] || [ "$secs" -gt 5400 ]; then
  log "pilot failed or too slow; full F1 NOT started (decide manually)"; exec bash
fi
{ echo "base commit: $(git rev-parse HEAD)"; git status --porcelain; } > "$BASE/provenance_f1.txt"
git diff > "$BASE/provenance_f1.diff"
log "F1 suite start (15 runs, the pilot run is reused)"
"$PY" run_suite.py --output-root "$OUT" --studies f1 --timeout 7200 2>&1 | tee "$OUT/suite_driver_f1.log"
log "F1 suite rc=${PIPESTATUS[0]}"
"$PY" analyze_suite.py --root "$OUT" --reanalyze > "$OUT/analysis_driver_f1.log" 2>&1; log "analysis rc=$?"
"$PY" $BASE/tools/m1_summary.py "$OUT" f1 2>&1 | tee "$OUT/f1_summary.txt"
touch "$BASE/F1_DONE"; log "F1 done"
exec bash
