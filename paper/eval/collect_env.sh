#!/usr/bin/env bash
# Snapshot what a local run ran on, next to its results: the paper's
# reproducibility table is built from these files. Run it after Maya has started
# on the rep's config, before the harness.
#   MAYA_DIR=~/project-maya MAYA_CONFIG=~/project-maya/maya-glm-maya-s.eval-r0.json \
#       paper/eval/collect_env.sh results/paper/env_maya-s_r0
set -uo pipefail
OUT="${1:?usage: collect_env.sh <out-dir>}"; mkdir -p "$OUT"
MAYA_DIR="${MAYA_DIR:-$HOME/project-maya}"
BASE="${MAYA_BASE_URL:-http://127.0.0.1:8080/v1}"
{
  echo "# date";            date -Is
  echo "# benchcad commit"; git rev-parse HEAD; git status --short | head
  echo "# maya version";    cat "$MAYA_DIR/VERSION" 2>/dev/null; git -C "$MAYA_DIR" rev-parse HEAD 2>/dev/null
  echo "# gpu";             nvidia-smi --query-gpu=name,memory.total,driver_version,power.limit --format=csv 2>&1
  echo "# cpu / ram";       lscpu | grep -E "Model name|^CPU\(s\)"; free -g | head -2
  echo "# MAYA_* env";      env | grep '^MAYA_' | grep -v KEY
} > "$OUT/env.txt"
curl -sS "$BASE/models" > "$OUT/models.json" 2>&1
curl -sS "${BASE%/v1}/props" > "$OUT/props.json" 2>&1       # sampling defaults (seed), context, slots, vision
if [ -n "${MAYA_CONFIG:-}" ]; then
  cp "$MAYA_CONFIG" "$OUT/"
  [ -f "${MAYA_CONFIG%.json}.meta.json" ] && cp "${MAYA_CONFIG%.json}.meta.json" "$OUT/"
fi
echo "wrote $OUT"
