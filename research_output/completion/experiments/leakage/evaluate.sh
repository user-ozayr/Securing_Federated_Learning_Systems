#!/usr/bin/env bash
# E6 evaluation: seed 101, 8 trials per (model state, batch size), three shards in
# parallel (one thread each on the 3-vCPU host), then merge and draw the figures.
# Attack setting from calibrate.sh: TV weight 0.05, 2000 iterations, 2 restarts.
cd "$(dirname "$0")/../../../.." || exit 1
export PYTHONPATH=src OMP_NUM_THREADS=1
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
OUT=research_output/completion/experiments/leakage/evaluation
ARGS=(--output-dir "$OUT" --trials 8 --batch-sizes 1 2 4 8 --iterations 2000 --restarts 2
      --tv-weight 0.05 --seed 101 --threads 1 --num-shards 3)
mkdir -p "$OUT"
for shard in 0 1 2; do
  $PY run_leakage_study.py "${ARGS[@]}" --shard $shard > "$OUT/shard_$shard.log" 2>&1 &
done
wait
$PY run_leakage_study.py "${ARGS[@]}" --merge > "$OUT/merge.log" 2>&1 \
  && $PY research_output/completion/tools/leakage_figures.py "$OUT" > "$OUT/figures.log" 2>&1
echo "exit=$?" > "$OUT/DONE"
