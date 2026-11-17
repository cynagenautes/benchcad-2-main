#!/usr/bin/env bash
# Snapshot what a local run ran on, next to its results: the paper's
# reproducibility table is built from these files.
#   MAYA_DIR=~/project-maya paper/eval/collect_env.sh results/paper/env_maya-s.txt
set -uo pipefail
OUT="${1:?usage: collect_env.sh <out.txt>}"
MAYA_DIR="${MAYA_DIR:-$HOME/project-maya}"
BASE="${MAYA_BASE_URL:-http://127.0.0.1:8080/v1}"
{
  echo "# date";            date -Is
  echo "# benchcad commit"; git rev-parse HEAD; git status --short | head
  echo "# maya version";    cat "$MAYA_DIR/VERSION" 2>/dev/null; git -C "$MAYA_DIR" rev-parse HEAD 2>/dev/null
  echo "# maya /v1/models"; curl -sS "$BASE/models" 2>&1 | head -c 4000; echo
  echo "# gpu";             nvidia-smi --query-gpu=name,memory.total,driver_version,power.limit --format=csv 2>&1
  echo "# cpu / ram";       lscpu | grep -E "Model name|^CPU\(s\)"; free -g | head -2
  echo "# MAYA_* env";      env | grep '^MAYA_' | grep -v KEY
} > "$OUT"
echo "wrote $OUT"
