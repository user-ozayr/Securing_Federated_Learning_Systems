#!/usr/bin/env bash
# E6 attack calibration on seed 7 (the evaluation uses seed 101): single images,
# both model states, total-variation weight swept. The setting that reconstructs
# best from the plaintext (individual) view is then used for the evaluation.
cd "$(dirname "$0")/../../../.." || exit 1
export PYTHONPATH=src OMP_NUM_THREADS=1
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
OUT=research_output/completion/experiments/leakage/calibration
mkdir -p "$OUT"
for tv in 0 0.001 0.01 0.05; do
  $PY run_leakage_study.py --output-dir "$OUT/tv$tv" --trials 3 --batch-sizes 1 \
    --iterations 3000 --restarts 2 --tv-weight "$tv" --seed 7 --threads 1 > "$OUT/tv$tv.log" 2>&1 &
done
wait
echo done > "$OUT/DONE"
