"""Write a Maya run config for one evaluation rep, from the config Maya's setup wrote.

    uv run python paper/eval/maya_config.py ~/project-maya/maya-glm-maya-s.json --rep 0 \
        [--repeatable] [--expert-cache 9400] [--ram-gb 40] [--parallel 1] [--loop-guard off] \
        [--thinking-budget 0] [--out ~/project-maya/maya-glm-maya-s.eval-r0.json]

then start Maya on it (./maya.sh --config <out>) and run the harness for that rep.

Why a config and not the request: Maya's Responses API (/v1/responses, what maya/
speaks) refuses a `seed` field ("unsupported Responses parameter"), so the seed is
the run config's `sampling.seed` - one per server start, one start per rep.

What it sets (the eval conditions of paper/PLAN.md section 2):
  sampling      temperature 1.0, top_p 0.95 (GLM-5.3-Flash's card; also on Maya-XS,
                whose own tuned default is 0.7 / min_p 0.05), seed = --seed-base + rep
  thinking_budget  --thinking-budget (0 = no cap: the harness's 128k reply cap governs)
  loop_guard    --loop-guard (off by default: it rewrites the conversation and adds
                server-written messages, which is not the model's zero-shot behaviour)
  --repeatable  Maya's "Repeatable answers" settings (docs/SETTINGS.md): no background
                tier moves, no re-timing, prompt numerics independent of the expert
                cache, and --expert-cache / --ram-gb fixed when given (take N a little
                under what the start log's `tiers warm` line shows). --cpu-lane-off
                takes the CPU lane away entirely (4-10 % slower decode, the same tokens
                after every restart).

Everything set here is printed and kept in the output file (and <out>.meta.json
says which rep and seed it is); paper/eval/collect_env.sh copies both next to the results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPEATABLE_ENV = {"MAYA_GLM_PROMOTE": "0",        # no background moves between the tiers
                  "MAYA_GLM_CPU_RETIME": "0",     # the CPU-lane split is not re-planned mid-run
                  "MAYA_GLM_PREFILL_STABLE": "1"}  # a prompt's numbers do not depend on the expert cache


def set_arg(args: list, flag: str, value: str | None) -> list:
    """args without `flag <v>`, then with `flag value` when value is given."""
    out, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if str(a) == flag:
            skip = True
            continue
        out.append(a)
    return out + ([flag, value] if value is not None else [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path, help="the maya-<model>.json Maya's setup wrote")
    ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--seed-base", type=int, default=1000)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--thinking-budget", type=int, default=0)
    ap.add_argument("--loop-guard", choices=("on", "off"), default="off")
    ap.add_argument("--parallel", type=int, default=None, help="Maya's slots (1 for bit-repeatable runs)")
    ap.add_argument("--repeatable", action="store_true")
    ap.add_argument("--cpu-lane-off", action="store_true")
    ap.add_argument("--expert-cache", type=int, default=None)
    ap.add_argument("--ram-gb", type=float, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    cfg = json.loads(a.config.read_text())
    sampling = {k: v for k, v in (cfg.get("sampling") or {}).items() if k not in ("min_p", "top_k")}
    sampling.update(temperature=a.temperature, top_p=a.top_p, seed=a.seed_base + a.rep)
    cfg["sampling"] = sampling
    cfg["thinking_budget"] = a.thinking_budget
    cfg["loop_guard"] = a.loop_guard == "on"
    env = dict(cfg.get("env") or {})
    args = list(cfg.get("args") or [])
    if a.parallel is not None:
        args = set_arg(args, "--parallel", str(a.parallel))
    if a.repeatable:
        env.update(REPEATABLE_ENV)
        if a.expert_cache is not None:
            args = set_arg(args, "--expert-cache", str(a.expert_cache))
        if a.ram_gb is not None:
            env["MAYA_GLM_RAM_GB"] = str(a.ram_gb)
    if a.cpu_lane_off:
        env["MAYA_GLM_CPU_LANE"] = "0"
    cfg["env"], cfg["args"] = env, args

    out = a.out or a.config.with_name(f"{a.config.stem}.eval-r{a.rep}.json")
    out.write_text(json.dumps(cfg, indent=2) + "\n")
    # what this file is, beside it (not inside: Maya's config has no field for it)
    out.with_suffix(".meta.json").write_text(json.dumps(
        {"rep": a.rep, "seed": sampling["seed"], "repeatable": a.repeatable, "cpu_lane_off": a.cpu_lane_off,
         "from": str(a.config)}, indent=1) + "\n")
    print(json.dumps({"out": str(out), "sampling": sampling, "thinking_budget": cfg["thinking_budget"],
                      "loop_guard": cfg["loop_guard"], "env": env,
                      "parallel": next((args[i + 1] for i, x in enumerate(args[:-1]) if x == "--parallel"), None)},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
