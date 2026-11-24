#!/usr/bin/env bash
# Plaintext replays for the sum-only divergence diagnostic (README.md in this directory).
# Each replay starts from the stored configuration of a plaintext FedAvg run of E1
# and replaces only the aggregation arithmetic (tools/sum_only_replay.py).
#   fp1e6  : S = 10^6, the scale of the sum-only SPDZ2k runs
#   fp2p40 : S = 2^40, a control with a much finer, power-of-two scale
set -u
REPO=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
DIAG=$REPO/research_output/completion/experiments/diagnostics/sum_only_divergence
OUT=$DIAG/replays
RUNS=$REPO/research_output/completion/experiments/runs
cd "$REPO" || exit 1
# same interpreter settings as the suite (suite.run_one); the worktree's src first
export PYTHONPATH="$REPO/src" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 RAY_DEDUP_LOGS=0
unset FL_MTD_SECRET

replay() {  # scale label attack seed
  local scale=$1 label=$2 attack=$3 seed=$4
  local name="replay_${label}__${attack}__s${seed}"
  local dir="$OUT/$name"
  if [ -f "$dir/replay_metadata.json" ] && grep -q '"status": "completed"' "$dir/replay_metadata.json"; then
    echo "skip $name (completed)"; return
  fi
  if [ -e "$dir" ]; then
    mkdir -p "$DIAG/failed_replays"
    mv "$dir" "$DIAG/failed_replays/${name}_$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  mkdir -p "$dir"
  echo "$(date -u +%FT%TZ) start $name"
  "$PY" research_output/completion/tools/sum_only_replay.py \
    --config "$RUNS/e1/e1__baseline__${attack}__s${seed}/config.yaml" \
    --scale "$scale" --name "$name" --output-dir "$dir" \
    --compare "spdz2k_sum_only=e1/e1__smpc_only__${attack}__s${seed}" \
    --compare "fedavg=e1/e1__baseline__${attack}__s${seed}" > "$dir/run.log" 2>&1
  local rc=$?
  echo "$(date -u +%FT%TZ) end $name rc=$rc"
}

for seed in 101 102 103; do
  for attack in none backdoor label_flip random_noise scaled_replacement; do
    replay 1000000 fp1e6 "$attack" "$seed"
  done
done
for seed in 101 102 103; do
  for attack in none backdoor; do
    replay 1099511627776 fp2p40 "$attack" "$seed"
  done
done
echo "$(date -u +%FT%TZ) all replays done"
"$PY" research_output/completion/tools/sum_only_divergence.py research_output/completion "$DIAG"
rc=$?
echo "$(date -u +%FT%TZ) analysis rc=$rc"
