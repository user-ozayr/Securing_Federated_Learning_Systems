#!/usr/bin/env bash
# Test report at the final code commit, plus a supplementary fresh-clone check of
# that commit (the full independent validation ran at 99366f7; later commits only
# touch the post-run analysis/report tooling and its tests).
set -u
THESIS=/home/ubuntu/gemini/fl-security-research-spdz2k-thesis
C=$THESIS/research_output/completion
OUT=$C/independent_validation
PY=/home/ubuntu/gemini/fl-security-research/.venv311/bin/python
export FL_MPSPDZ_HOME=/home/ubuntu/gemini/MP-SPDZ-v0.4.3 FL_MPSPDZ_STARTUP_TIMEOUT=0.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset FL_MTD_SECRET
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

cd "$THESIS" || exit 1
{
  echo "# pytest -v, worktree $THESIS, commit $(git rev-parse HEAD), $(now)"
  echo "# tracked files modified in the worktree: $(git status --porcelain --untracked-files=no | wc -l)"
  PYTHONPATH=src $PY -m pytest -v -p no:cacheprovider; echo "exit $?"
  echo
  echo "# real MP-SPDZ integration tests (FL_RUN_MPSPDZ_TESTS=1), $(now)"
  PYTHONPATH=src FL_RUN_MPSPDZ_TESTS=1 $PY -m pytest -v -p no:cacheprovider tests/test_mpspdz_integration.py
  echo "exit $?"
} > "$C/test_results.txt" 2>&1

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FRESH=/home/ubuntu/gemini/fresh_validation_clone_$STAMP
if [ -e "$FRESH" ]; then echo "refusing to reuse $FRESH" >&2; exit 2; fi
git clone --quiet --branch research/thesis-completion --single-branch /home/ubuntu/gemini/fl-security-research "$FRESH" || exit 3
cd "$FRESH" || exit 4
{
  echo "supplementary fresh clone: $FRESH"
  echo "commit: $(git rev-parse HEAD)"
  echo "date (UTC): $(now)"
  echo "tracked files modified in clone: $(git status --porcelain --untracked-files=no | wc -l)"
  echo "changes since the commit of the full independent validation (99366f7):"
  git diff --stat 99366f7 HEAD
} > "$OUT/supplementary_clone_info.txt"
FL_DATA_ROOT="$THESIS/data" PYTHONPATH="$FRESH/src" $PY -m pytest -v -p no:cacheprovider \
  > "$OUT/pytest_fresh_clone_final_commit.txt" 2>&1; rc=$?
echo "$(now) pytest exit $rc: $(tail -n 1 "$OUT/pytest_fresh_clone_final_commit.txt")" >> "$OUT/supplementary_clone_info.txt"
PYTHONPATH="$FRESH/src" $PY "$C/tools/import_provenance_check.py" "$FRESH" /home/ubuntu/gemini/fl-security-research/src \
  > "$OUT/import_provenance_fresh_clone_final_commit.txt" 2>&1; rc=$?
echo "$(now) import provenance exit $rc: $(tail -n 1 "$OUT/import_provenance_fresh_clone_final_commit.txt")" >> "$OUT/supplementary_clone_info.txt"
cat "$OUT/supplementary_clone_info.txt"
grep -E "passed|failed|^exit|^# " "$C/test_results.txt"
