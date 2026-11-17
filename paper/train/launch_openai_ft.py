"""Start the OpenAI fine-tuning job -- or, by default, stop right before it.

    # dry run (the default): checks everything, spends nothing, sends nothing
    uv run python paper/train/launch_openai_ft.py data/ft_v1 --base-model <fine-tunable-model-id>

    # the real thing: uploads train/val and creates the job
    OPENAI_API_KEY=... uv run python paper/train/launch_openai_ft.py data/ft_v1 \
        --base-model <fine-tunable-model-id> --execute

What the dry run checks, in order, and refuses on:
  - the contamination report (paper/train/contamination.py) exists and passed,
    and was made from the same JSONL bytes that would be uploaded;
  - every JSONL line parses, has system / user / assistant, the assistant
    answer is one ```submit fence, every image is a PNG data URL;
  - the file sizes, the example count, and the estimated training tokens.
It prints what --execute would send. With OPENAI_API_KEY set it also asks the
API (read-only: models.retrieve) whether --base-model exists for this key.

Which models accept fine-tuning, with images, changes over time: check OpenAI's
fine-tuning guide on the day and pass that id. No model id is assumed here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

FENCE = re.compile(r"\A```submit\n.*\n```\Z", re.S)


def image_tokens_tiles(w: int, h: int) -> int:
    """The documented 'detail: high' tile rule (85 + 170 per 512 px tile after
    fitting in 2048 and scaling the short side to 768). Newer models count
    patches instead; this is an estimate to size the bill, not the bill."""
    s = min(1.0, 2048 / max(w, h))
    w, h = w * s, h * s
    s = min(1.0, 768 / min(w, h))
    w, h = w * s, h * s
    return 85 + 170 * (-(-int(w) // 512)) * (-(-int(h) // 512))


def check_jsonl(path: Path) -> dict:
    from PIL import Image
    import io
    n, text_chars, img_tokens, problems = 0, 0, 0, []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        try:
            ex = json.loads(line)
            roles = [m["role"] for m in ex["messages"]]
            if roles != ["system", "user", "assistant"]:
                problems.append(f"{path.name}:{i} roles {roles}")
            ans = ex["messages"][2]["content"]
            if not FENCE.match(ans):
                problems.append(f"{path.name}:{i} assistant is not one ```submit fence")
            for m in ex["messages"]:
                parts = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
                for p in parts:
                    if p["type"] == "text":
                        text_chars += len(p["text"])
                    elif p["type"] == "image_url":
                        url = p["image_url"]["url"]
                        if not url.startswith("data:image/png;base64,"):
                            problems.append(f"{path.name}:{i} image is not a PNG data URL")
                            continue
                        with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))) as im:
                            img_tokens += image_tokens_tiles(*im.size)
            n += 1
        except Exception as e:                                # noqa: BLE001
            problems.append(f"{path.name}:{i} {type(e).__name__}: {e}")
    return {"file": str(path), "examples": n, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "est_text_tokens": text_chars // 4, "est_image_tokens": img_tokens, "problems": problems}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ft", type=Path)
    ap.add_argument("--base-model", required=True, help="a model id OpenAI fine-tunes with images, today")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--suffix", default="cad-synth-v1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--price-per-mtok", type=float, default=None,
                    help="training price per 1M tokens for --base-model, from OpenAI's pricing page today")
    ap.add_argument("--execute", action="store_true", help="really upload and create the job")
    a = ap.parse_args(argv)

    stats = json.loads((a.ft / "stats.json").read_text())
    rep_path = a.ft / "contamination.json"
    if not rep_path.exists():
        raise SystemExit(f"{rep_path} missing: run paper/train/contamination.py first")
    rep = json.loads(rep_path.read_text())
    if not rep.get("pass"):
        raise SystemExit(f"{rep_path}: contamination check did not pass; nothing is uploaded")

    files = {k: a.ft / f"{k}.jsonl" for k in ("train", "val") if (a.ft / f"{k}.jsonl").exists()}
    if "train" not in files:
        raise SystemExit(f"{a.ft}/train.jsonl missing")
    checks = {k: check_jsonl(p) for k, p in files.items()}
    for k, c in checks.items():
        if c["sha256"] != stats["files"][k]["sha256"]:
            raise SystemExit(f"{files[k]} changed since build_openai_jsonl.py wrote it; rebuild and re-check")
        if c["problems"]:
            raise SystemExit(f"{files[k]}: {len(c['problems'])} problems, first: {c['problems'][:3]}")

    tr = checks["train"]
    per_epoch = tr["est_text_tokens"] + tr["est_image_tokens"]
    plan = {"base_model": a.base_model, "method": {"type": "supervised", "supervised": {
                "hyperparameters": {"n_epochs": a.epochs}}},
            "suffix": a.suffix, "seed": a.seed,
            "files": {k: {"examples": c["examples"], "MB": round(c["bytes"] / 1e6, 1), "sha256": c["sha256"][:16]}
                      for k, c in checks.items()},
            "est_tokens_per_epoch": per_epoch, "est_billed_tokens": per_epoch * a.epochs,
            "est_usd": round(per_epoch * a.epochs / 1e6 * a.price_per_mtok, 2) if a.price_per_mtok else None,
            "contamination_report": {"benchcad_trees": rep["benchcad_trees"],
                                     "files_hashed": rep["benchcad_files_hashed"],
                                     "reference_solids": rep["benchcad_reference_solids"]}}
    print(json.dumps(plan, indent=1))

    key = os.environ.get("OPENAI_API_KEY")
    if key:
        import openai
        try:
            m = openai.OpenAI().models.retrieve(a.base_model)
            print(f"models.retrieve({a.base_model!r}): exists for this key (owned_by={m.owned_by}); "
                  "whether it is fine-tunable is decided by jobs.create")
        except openai.NotFoundError:
            raise SystemExit(f"{a.base_model!r} is not a model this key can see")
    else:
        print("OPENAI_API_KEY not set: the base model was not checked against the API")

    if not a.execute:
        print("\nDRY RUN: nothing was uploaded and no job was created. Add --execute to start training.")
        return 0

    if not key:
        raise SystemExit("--execute needs OPENAI_API_KEY")
    import openai
    client = openai.OpenAI()
    ids = {}
    for k, p in files.items():
        with p.open("rb") as f:
            ids[k] = client.files.create(file=f, purpose="fine-tune").id
        print(f"uploaded {p} -> {ids[k]}")
    job = client.fine_tuning.jobs.create(
        model=a.base_model, training_file=ids["train"], validation_file=ids.get("val"),
        suffix=a.suffix, seed=a.seed, method=plan["method"],
        metadata={"dataset_sha256": checks["train"]["sha256"][:32]})
    record = {"job_id": job.id, "status": job.status, "created": time.time(), "file_ids": ids, "plan": plan}
    (a.ft / f"job_{job.id}.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"created fine-tuning job {job.id} ({job.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
