"""Synthetic samples -> OpenAI chat fine-tuning JSONL (vision SFT), train/val split.

    uv run python paper/train/build_openai_jsonl.py data/synth_v1 --out data/ft_v1 \
        [--val-frac 0.1] [--holdout-family ribbed_plate]

One example per sample, single turn, in the format of OpenAI's chat fine-tuning
files: system / user (an instruction + the four-view sheet as an image_url data
URL) / assistant (the answer as the BenchCAD harness reads one: a ```submit fence
holding the whole program). The instruction is our own wording, not BenchCAD's
TASK.md, so a gain on BenchCAD is not a gain from having seen its prompt.

--holdout-family keeps a whole family out of train AND val and writes it to
ood.jsonl: an out-of-family check that needs no BenchCAD case.

Writes train.jsonl, val.jsonl, (ood.jsonl), manifest.json (which sample went
where, with the sha256 of every file sent), stats.json.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
from pathlib import Path

SYSTEM = ("You are a CAD engineer. You write CadQuery (Python) programs that rebuild a "
          "mechanical part from images of it.")
USER = ("The image is a 2x2 sheet of four parallel-projection views of one part, all at the "
        "same scale, each camera looking at the part's centre with world +Z up in the image: "
        "top-left from about (-1,-1,1), top-right from exactly (1,1,1), bottom-left from about "
        "(-1,1,-1), bottom-right from about (1,-1,-1); the approximate cameras are a few degrees "
        "off. Write one complete CadQuery program that builds the part and leaves the solid in "
        "`result`. Answer with the program in a ```submit fenced block and nothing else.")


def example(sample: Path) -> dict:
    img = base64.b64encode((sample / "views.png").read_bytes()).decode()
    program = (sample / "program.py").read_text().rstrip() + "\n"
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": USER},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + img, "detail": "high"}}]},
        {"role": "assistant", "content": "```submit\n" + program + "```"}]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("synth", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--holdout-family", action="append", default=[])
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    samples = sorted(p.parent for p in a.synth.glob("*/meta.json") if (p.parent / "views.png").exists())
    if not samples:
        raise SystemExit(f"{a.synth}: no rendered samples (meta.json + views.png)")
    by_fam: dict[str, list[Path]] = {}
    for s in samples:
        by_fam.setdefault(json.loads((s / "meta.json").read_text())["family"], []).append(s)
    unknown = set(a.holdout_family) - set(by_fam)
    if unknown:
        raise SystemExit(f"--holdout-family {sorted(unknown)}: not in {sorted(by_fam)}")

    rng = random.Random(a.seed)
    split: dict[str, list[Path]] = {"train": [], "val": [], "ood": []}
    for fam, ss in sorted(by_fam.items()):
        if fam in a.holdout_family:
            split["ood"] += ss
            continue
        ss = ss[:]
        rng.shuffle(ss)
        k = max(1, round(len(ss) * a.val_frac)) if len(ss) > 1 else 0
        split["val"] += ss[:k]
        split["train"] += ss[k:]

    a.out.mkdir(parents=True, exist_ok=True)
    manifest, stats = {}, {}
    for name, ss in split.items():
        if not ss:
            continue
        path = a.out / f"{name}.jsonl"
        with path.open("w") as f:
            for s in ss:
                f.write(json.dumps(example(s)) + "\n")
        manifest[name] = [{"sample": s.name, "sha256": json.loads((s / "meta.json").read_text())["sha256"]}
                          for s in ss]
        stats[name] = {"examples": len(ss), "bytes": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (a.out / "stats.json").write_text(json.dumps(
        {"source": str(a.synth), "seed": a.seed, "val_frac": a.val_frac,
         "holdout_family": a.holdout_family, "system": SYSTEM, "user": USER, "files": stats}, indent=1) + "\n")
    print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
