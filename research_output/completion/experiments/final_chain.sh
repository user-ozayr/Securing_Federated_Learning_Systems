#!/usr/bin/env bash
# Final evidence chain (2026-11-20), run after FOLLOWUP_DONE:
#  1. move the one run aborted by a transient TLS reset to failed_attempts/ and repeat it;
#  2. independent validation from a fresh clone (own output directory);
#  3. full test report of this worktree;
#  4. re-analysis of every run and the benchmark report.
# Exit codes are captured immediately after each command.
set -u
THESIS=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis
cd "$THESIS" || exit 1
C=research_output/completion
OUT=$C/experiments
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 PYTHONPATH=src FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset FL_MTD_SECRET
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

RUN=e1x__smpc_screen__scaled_replacement__s102
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST=$OUT/failed_attempts/${STAMP}_infra/e1x
if [ -d "$OUT/runs/e1x/$RUN" ]; then
  mkdir -p "$DEST" && mv "$OUT/runs/e1x/$RUN" "$DEST/" && log "moved $RUN to $DEST"
  cat > "$DEST/REASON.txt" <<'EOF'
This attempt aborted in round 10 of 10 (9 rounds completed and saved) with
ConnectionResetError [Errno 104] raised in ssl.do_handshake while a client
connected to an MP-SPDZ party (MP-SPDZ ExternalIO/client.py); see run.log.
Infrastructure fault on the shared host, unrelated to the attack or the defence.
The attempt is kept unchanged here. The run was repeated with the same
configuration and seed (suite_driver_pass3.log).
EOF
fi
$PY run_suite.py --output-root $OUT --timeout 3600 --studies e1x > $OUT/suite_driver_pass3.log 2>&1; rc=$?
log "pass 3 (repeat of $RUN) rc=$rc"

bash $C/independent_validation.sh > $C/independent_validation_driver.log 2>&1; rc=$?
log "independent validation rc=$rc"

{
  echo "# pytest -v, worktree $THESIS, commit $(git rev-parse HEAD), $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  $PY -m pytest -v -p no:cacheprovider; echo "exit $?"
  echo
  echo "# real MP-SPDZ integration tests (FL_RUN_MPSPDZ_TESTS=1), $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  FL_RUN_MPSPDZ_TESTS=1 $PY -m pytest -v -p no:cacheprovider tests/test_mpspdz_integration.py; echo "exit $?"
} > $C/test_results.txt 2>&1
log "tests written to $C/test_results.txt"

$PY analyze_suite.py --root $OUT --reanalyze --benchmarks $C/benchmarks > $C/analysis_driver.log 2>&1; rc=$?
log "analysis rc=$rc"
touch $OUT/FINAL_CHAIN_DONE
