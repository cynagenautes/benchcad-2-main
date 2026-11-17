"""Did two runs of the same cases with the same seed give the same episodes?

    uv run python paper/eval/compare_runs.py results/paper/repeat_a.json results/paper/repeat_b.json

Per case: the same number of calls with the same output tokens each (the model
wrote the same lengths, call by call), the same submitted artifact (sha256) and
the same score. Identical on all three is what a bit-repeatable Maya gives;
anything else names the first call where the two runs parted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def cases(path: Path) -> dict:
    d = json.loads(path.read_text())
    return {r["case_id"]: r for r in d["cases"]}


def headline(r: dict):
    s = r.get("score")
    return s.get("score") if isinstance(s, dict) else s


def main(argv=None) -> int:
    a, b = (Path(p) for p in (argv or sys.argv[1:]))
    ra, rb = cases(a), cases(b)
    both = sorted(set(ra) & set(rb))
    same_all = 0
    for cid in both:
        x, y = ra[cid], rb[cid]
        ox = [c["output"] for c in (x.get("tokens") or {}).get("per_call", [])]
        oy = [c["output"] for c in (y.get("tokens") or {}).get("per_call", [])]
        parted = next((i for i, (p, q) in enumerate(zip(ox, oy)) if p != q), None)
        if parted is None and len(ox) != len(oy):
            parted = min(len(ox), len(oy))
        same_art = x.get("artifact_sha256") == y.get("artifact_sha256")
        same_score = headline(x) == headline(y)
        ok = parted is None and same_art and same_score
        same_all += ok
        print(f"{cid:40s} {'SAME' if ok else 'DIFF'}  calls {len(ox)}/{len(oy)}"
              + ("" if parted is None else f"  parted at call {parted + 1}")
              + f"  artifact {'=' if same_art else '!='}  score {headline(x)} / {headline(y)}")
    print(f"\n{same_all}/{len(both)} cases identical"
          + (f"; only in one run: {sorted(set(ra) ^ set(rb))}" if set(ra) ^ set(rb) else ""))
    return 0 if same_all == len(both) else 1


if __name__ == "__main__":
    raise SystemExit(main())
