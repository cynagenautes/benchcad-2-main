#!/usr/bin/env bash
# The zero-shot evaluation of paper/PLAN.md, stage by stage. Nothing runs by itself:
# pick a stage, read it, run it. Every run writes results/paper/<name>.json and
# resumes with the same command.
#
#   0       plumbing      mock/oracle on the 9 examples (no model, no Maya)
#   1       pilot         Maya on the 9 examples: tokens/case and hours/case, before any long run
#   main    the run       Maya on the Public set, one rep per Maya start (REP=0,1,2)
#   repeat  repeatability the same 6 cases twice under one seed (RUN=a, restart Maya, RUN=b),
#                         then paper/eval/compare_runs.py
#   ref     optional      the same model through OpenRouter, for a cloud-vs-local line
#
# Per rep: write the config (paper/eval/maya_config.py ... --rep $REP), start Maya on it,
# snapshot it (paper/eval/collect_env.sh), then run this. The script checks Maya's /props
# for the seed that rep should have (SEED_BASE + REP) and stops on a mismatch.
set -euo pipefail
cd "$(dirname "$0")/../.."

STAGE="${1:?usage: paper/eval/run_matrix.sh <0|1|main|repeat|ref> [extra harness flags]}"; shift || true
OUT=results/paper; mkdir -p "$OUT"
CASES_PUBLIC="${CASES_PUBLIC:-$HOME/.cache/benchcad/benchcad-2.0-public}"   # tools/run_core.sh --set public puts it here
TIER="${TIER:-maya-s}"                       # a label: the Maya quant the server has loaded
MODEL_ID="${MAYA_MODEL_ID:-glm-5.3-flash}"   # the id Maya's /v1/models lists
EFFORT="${EFFORT:-max}"                      # GLM-5.3-Flash's own default and its card's benchmark setting
REP="${REP:-0}"
SEED_BASE="${SEED_BASE:-1000}"
CTX="${MAYA_CONTEXT_TOKENS:?set MAYA_CONTEXT_TOKENS to the context Maya was started with}"
WORKERS="${WORKERS:-1}"                      # <= Maya's --parallel; 1 for the repeatability stage
MAX_EXECS="${MAX_EXECS:-2}"                  # sandbox runs at once, 2 GB each, on the harness machine
BASE="${MAYA_BASE_URL:-http://127.0.0.1:8080/v1}"

check_seed() {   # the server must hold the seed of this rep
  local want=$((SEED_BASE + REP)) got
  got=$(curl -sS "${BASE%/v1}/props" | uv run --no-project python -c \
        "import json,sys; print(json.load(sys.stdin)['default_generation_settings']['params'].get('seed'))") \
    || { echo "cannot read ${BASE%/v1}/props: is Maya up?" >&2; exit 1; }
  [ "$got" = "$want" ] || { echo "Maya's seed is $got, rep $REP needs $want: start it on that rep's config" >&2; exit 1; }
}

run() {  # run <name> <model> <cases> [flags...]
  local name=$1 model=$2 cases=$3; shift 3
  uv run python harness/run.py --model "$model" --effort "$EFFORT" --rep "$REP" --cases "$cases" \
      --workers "$WORKERS" --max-execs "$MAX_EXECS" --out "$OUT/$name.json" --resume "$@"
}

case "$STAGE" in
  0)      uv run python harness/run.py --model mock/oracle --cases examples --rounds 1 --out "$OUT/oracle.json" ;;
  1)      check_seed; run "pilot_${TIER}_${EFFORT}_r${REP}" "maya/$MODEL_ID" examples --context-tokens "$CTX" "$@" ;;
  main)   check_seed; run "main_${TIER}_${EFFORT}_r${REP}" "maya/$MODEL_ID" "$CASES_PUBLIC" --context-tokens "$CTX" "$@" ;;
  repeat) check_seed; RUN="${RUN:?RUN=a or RUN=b}"
          # one case per task, the first of each, so both runs see the same list
          # (copied, not linked: the harness does not follow links; the layout task<N>/cases/<id> is kept)
          LIST="$OUT/repeat_cases"; if [ ! -d "$LIST" ]; then
            for t in "$CASES_PUBLIC"/task*; do c=$(ls -d "$t"/cases/* | head -1)
              mkdir -p "$LIST/$(basename "$t")/cases"; cp -r "$c" "$LIST/$(basename "$t")/cases/"; done; fi
          run "repeat_${TIER}_${EFFORT}_${RUN}" "maya/$MODEL_ID" "$LIST" --context-tokens "$CTX" "$@" ;;
  ref)    run "ref_openrouter_${EFFORT}_r${REP}" "openrouter/z-ai/glm-5.3-flash" "$CASES_PUBLIC" "$@" ;;
  *)      echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
