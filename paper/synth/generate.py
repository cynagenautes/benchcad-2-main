"""Generate the synthetic four-view -> CadQuery training set.

    uv run python paper/synth/generate.py --n 400 --out data/synth_v1 --seed 0

Per sample <out>/<family>_<k>/:
    program.py   the training target (a complete program leaving `result`)
    gt.step      what it builds
    views.png    the 2x2 four-view sheet, rendered the way T3 renders (the harness's
                 own envs/common/bench_views.py, perturbed cameras, 700 px per view)
    meta.json    family, params, seed, sha256 of every file, volume and bbox

A program that fails to run, builds no solid or an invalid one is dropped and
counted; the summary (<out>/summary.json) records how many of each family survived.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from families import FAMILIES  # noqa: E402

CANARY = "paper-synth-v1"   # our own marker, so a leak of THIS set can be found too


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(src: str):
    import cadquery as cq
    ns: dict = {}
    exec(compile(src, "program.py", "exec"), ns)          # our own generated code, not untrusted input
    res = ns.get("result")
    if res is None:
        raise ValueError("no result")
    shape = res.val() if isinstance(res, cq.Workplane) else res
    if not shape.isValid():
        raise ValueError("invalid solid")
    if shape.Volume() <= 1e-6:
        raise ValueError("empty solid")
    return res, shape


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=400, help="samples to attempt (spread over the families)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--size", type=int, default=700, help="px per view (T3: 700)")
    ap.add_argument("--no-render", action="store_true", help="programs and STEP only (no VTK needed)")
    a = ap.parse_args(argv)

    import cadquery as cq
    if not a.no_render:
        from envs.common.bench_views import composite_for_step, perturbation

    a.out.mkdir(parents=True, exist_ok=True)
    master = random.Random(a.seed)
    stats = {f.name: {"ok": 0, "dropped": 0, "why": {}} for f in FAMILIES}
    for i in range(a.n):
        fam = FAMILIES[i % len(FAMILIES)]
        seed = master.getrandbits(32)
        params, src = fam.make(random.Random(seed))
        d = a.out / f"{fam.name}_{i:05d}"
        try:
            res, shape = build(src)
            d.mkdir(parents=True, exist_ok=True)
            (d / "program.py").write_text(src)
            cq.exporters.export(res, str(d / "gt.step"))
            files = ["program.py", "gt.step"]
            cams = None
            if not a.no_render:
                cams = perturbation(seed)
                composite_for_step(d / "gt.step", d / "views.png", size=a.size, perturb=cams)
                files.append("views.png")
            bb = shape.BoundingBox()
            meta = {"family": fam.name, "seed": seed, "params": params, "canary": CANARY,
                    "volume": round(shape.Volume(), 4),
                    "bbox": [round(v, 4) for v in (bb.xlen, bb.ylen, bb.zlen)],
                    "faces": len(shape.Faces()), "cameras": cams,
                    "sha256": {f: sha(d / f) for f in files}}
            (d / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
            stats[fam.name]["ok"] += 1
        except Exception as e:                              # noqa: BLE001 -- counted, not hidden
            why = f"{type(e).__name__}: {str(e)[:80]}"
            s = stats[fam.name]
            s["dropped"] += 1
            s["why"][why] = s["why"].get(why, 0) + 1
            if s["dropped"] <= 2:
                traceback.print_exc(limit=1)
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{a.n}", flush=True)
    summary = {"n_attempted": a.n, "seed": a.seed, "size": a.size, "rendered": not a.no_render,
               "n_ok": sum(s["ok"] for s in stats.values()), "families": stats}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: (v["ok"], v["dropped"]) for k, v in stats.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
