#!/usr/bin/env bash
# Follow-up after the first suite pass: archive failed attempts, retry
# non-completed runs (current commit), then run the isolated SPDZ2k benchmarks.
set -u
cd /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
OUT=research_output/completion/experiments
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 PYTHONPATH=src FL_MPSPDZ_STARTUP_TIMEOUT=0.5 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
while kill -0 104468 2>/dev/null; do sleep 30; done
echo "suite pass 1 finished $(date -u)"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
for meta in $OUT/runs/*/*/run_metadata.json; do
  if ! grep -q '"status": "completed"' "$meta"; then
    dir=$(dirname "$meta"); dest=$OUT/failed_attempts/$STAMP/$(basename $(dirname "$dir"))
    mkdir -p "$dest" && cp -r "$dir" "$dest/" && echo "archived $dir"
  fi
done
$PY run_suite.py --output-root $OUT --timeout 3600 > $OUT/suite_driver_pass2.log 2>&1
echo "suite pass 2 finished $(date -u) rc=$?"
$PY run_mpc_benchmark.py --output-dir research_output/completion/benchmarks --cap-seconds 1800 > research_output/completion/benchmarks_driver.log 2>&1
echo "benchmarks finished $(date -u) rc=$?"
touch $OUT/FOLLOWUP_DONE
