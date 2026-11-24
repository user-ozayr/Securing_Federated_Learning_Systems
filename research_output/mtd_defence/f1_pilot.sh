#!/usr/bin/env bash
# One SPDZ2k run of the final framework (seed 101, just-in-time attacker) to
# measure time and memory before the full F1 study. Samples used memory every 30 s.
set -u
REPO=/home/ubuntu/gemini/fl-security-research-mtd-defence
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
BASE=research_output/mtd_defence; OUT=$BASE/experiments
cd "$REPO" || exit 1
export PYTHONPATH="$REPO/src" FL_DATA_ROOT=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/data
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
( while true; do echo "$(date -u +%T) $(free -m | awk "/Mem:/{print \$3}") MB used, load $(cut -d" " -f1 /proc/loadavg)"; sleep 30; done ) > $BASE/f1_pilot_memory.log &
MON=$!
start=$(date +%s)
"$PY" run_suite.py --output-root "$OUT" --studies f1_pilot --timeout 7200 > "$OUT/suite_driver_f1_pilot.log" 2>&1
echo "rc=$? seconds=$(( $(date +%s) - start ))" > $BASE/f1_pilot_result.txt
kill $MON; touch $BASE/F1_PILOT_DONE
