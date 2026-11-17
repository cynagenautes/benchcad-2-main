#!/usr/bin/env bash
# The experiment matrix of paper/PLAN.md, one line per arm. Nothing here runs by
# itself: pick a stage, read it, run it. Every arm writes results/paper/<arm>.json
# and resumes with the same command.
#
#   stage 0  plumbing      mock/oracle on the 9 examples (no model, no key)
#   stage 1  pilot         maya on the 9 examples, one effort, 1 rep: tokens/case and hours/case
#   stage 2  main          maya tiers x {low, high} x 3 reps on Public; the cloud FP8 reference
#   stage 3  effort sweep  one tier x {none, low, high, max} on Public, 1 rep
#
# Maya: the tier is whatever the server at MAYA_BASE_URL has loaded (./maya.sh --model
# glm-maya-s, -m, -l ...). Restart the server per tier, set TIER to match, and record
# Maya's VERSION, its run config (context, thinking_budget, parallel) and nvidia-smi
# next to the results: paper/eval/collect_env.sh does that.
set -euo pipefail
cd "$(dirname "$0")/../.."

STAGE="${1:?usage: paper/eval/run_matrix.sh <0|1|2|3> [extra harness flags]}"; shift || true
OUT=results/paper; mkdir -p "$OUT"
CASES_PUBLIC="${CASES_PUBLIC:-$HOME/.cache/benchcad/benchcad-2.0-public}"   # where tools/run_core.sh --set public puts it
TIER="${TIER:-maya-s}"                                     # a label only: what the server has loaded
MODEL_ID="${MAYA_MODEL_ID:-glm-5.3-flash}"                 # the id Maya's /v1/models lists
CTX="${MAYA_CONTEXT_TOKENS:-262144}"                       # Maya's configured context, NOT the model's 1M
WORKERS="${WORKERS:-4}"                                    # <= Maya's parallel slots (up to 8 on GLM-5.3-Flash)
MAX_EXECS="${MAX_EXECS:-2}"                                # 2 GB each, on the machine running the harness

run() {  # run <arm> <model> <effort> <rep> <cases> [flags...]
  local arm=$1 model=$2 effort=$3 rep=$4 cases=$5; shift 5
  uv run python harness/run.py --model "$model" --effort "$effort" --rep "$rep" \
      --cases "$cases" --workers "$WORKERS" --max-execs "$MAX_EXECS" \
      --out "$OUT/${arm}_${effort}_r${rep}.json" --resume "$@"
}

case "$STAGE" in
  0) uv run python harness/run.py --model mock/oracle --cases examples --rounds 1 --out "$OUT/oracle.json" ;;
  1) run "pilot_${TIER}" "maya/$MODEL_ID" high 0 examples --context-tokens "$CTX" "$@" ;;
  2) for rep in 0 1 2; do for eff in low high; do
       run "main_${TIER}" "maya/$MODEL_ID" "$eff" "$rep" "$CASES_PUBLIC" --context-tokens "$CTX" "$@"
     done; done ;;
  2ref)   # the same model at the provider's precision, through OpenRouter: pin the provider and record it
     for rep in 0 1 2; do for eff in low high; do
       run "ref_openrouter" "openrouter/z-ai/glm-5.3-flash" "$eff" "$rep" "$CASES_PUBLIC" "$@"
     done; done ;;
  3) for eff in none low high max; do
       run "sweep_${TIER}" "maya/$MODEL_ID" "$eff" 0 "$CASES_PUBLIC" --context-tokens "$CTX" "$@"
     done ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
uv run python tools/summarize.py "$OUT"/*.json || true
