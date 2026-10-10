"""Score reader variants against the hand lists in experiments/gold.

    python experiments/reader_bench.py <variant> [<variant> ...] [--seeds N] [--dev] [--fresh] [--detail]

Development papers (used while changing prompts and code): legend, T2K.
Held-out papers (only looked at as scores): dune, ice_cube, super-k.
"""

import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from g4geoagent.agent import llm
from g4geoagent.agent.compare import check_quotes, claim_numbers
from g4geoagent.agent.runlog import RunLog
from g4geoagent.agent.schemas import Reading

ROOT = Path(__file__).parents[1]
TEXT, GOLD, OUT = ROOT / "runs/papers_test/text", ROOT / "experiments/gold", ROOT / "runs/reader_bench"
DEV, HELD_OUT = ["legend", "T2K"], ["dune", "ice_cube", "super-k"]
PARTIAL = {"super-k"}        # hand list covers only part of the paper: extra claims are not judged


def matches(claim, entry):
    numbers = claim_numbers(claim)
    wanted = [float(entry["value"])] + ([float(entry["alt"])] if "alt" in entry else [])
    if not any(math.isclose(n, w, rel_tol=1e-9) for n in numbers for w in wanted):
        return False
    where = f"{claim.quote} {claim.part} {claim.quantity} {claim.unit}".lower()
    return re.search(entry["key"], where) is not None


def score(reading, gold, documents, partial=False):
    built = [c for c in reading.claims if c.category != "not_geometry"]
    required = [e for e in gold if not e.get("optional")]
    found = [e for e in required if any(matches(c, e) for c in built)]
    numeric = [c for c in built if claim_numbers(c)]
    extra = [c for c in numeric if not any(matches(c, e) for e in gold)]
    return {"required": len(required), "found": len(found),
            "missed": [e["what"] for e in required if e not in found],
            "numeric": len(numeric), "extra": [] if partial else extra,
            "claims": len(reading.claims), "bad_quotes": len(check_quotes(reading, documents))}


def run(variant, paper, seed=0, fresh=False):
    """The reading of `paper` by `variant` with `seed`, from disk if it was made before."""
    from variants import VARIANTS
    file = OUT / variant / f"seed{seed}" / f"{paper}.json"
    if file.exists() and not fresh:
        return Reading.model_validate_json(file.read_text())
    file.parent.mkdir(parents=True, exist_ok=True)
    log_file = file.with_suffix(".jsonl")
    log_file.unlink(missing_ok=True)
    documents = {f"{paper}.txt": (TEXT / f"{paper}.txt").read_text()}
    reading = VARIANTS[variant](documents, RunLog(log_file))
    file.write_text(reading.model_dump_json(indent=1))
    return reading


def report(variant, seeds=1, fresh=False, detail=False, dev_only=False):
    """Scores of `variant`, summed over `seeds` independent runs."""
    papers = DEV if dev_only else DEV + HELD_OUT
    totals = {"dev": [0] * 6, "held-out": [0] * 6}
    recalls = {"dev": [], "held-out": []}
    for seed in range(seeds):
        llm.DEFAULT_OPTIONS["seed"] = seed
        with ThreadPoolExecutor(3) as pool:
            readings = list(pool.map(lambda p: run(variant, p, seed, fresh), papers))
        per_seed = {"dev": [0, 0], "held-out": [0, 0]}
        for paper, reading in zip(papers, readings):
            documents = {f"{paper}.txt": (TEXT / f"{paper}.txt").read_text()}
            s = score(reading, yaml.safe_load((GOLD / f"{paper}.yaml").read_text()), documents, paper in PARTIAL)
            name = "dev" if paper in DEV else "held-out"
            judged = 0 if paper in PARTIAL else s["numeric"]
            for i, v in enumerate([s["found"], s["required"], len(s["extra"]), judged, s["bad_quotes"], s["claims"]]):
                totals[name][i] += v
            per_seed[name][0] += s["found"]; per_seed[name][1] += s["required"]
            if detail:
                print(f"    seed {seed} {paper:9s} found {s['found']:2d}/{s['required']:2d} missed {s['missed']} "
                      f"extra {[f'{c.part}.{c.quantity}={c.value}' for c in s['extra']]}")
        for name, (found, required) in per_seed.items():
            if required:
                recalls[name].append(found / required)
    line = f"{variant:22s}"
    for name, (found, required, extra, judged, bad, claims) in totals.items():
        if required:
            line += (f" | {name}: recall {found / required:4.0%} (worst run {min(recalls[name]):4.0%})  "
                     f"extra {extra / max(judged, 1):4.0%}  bad quotes {bad / max(claims, 1):4.1%}  claims/run {claims / seeds:5.0f}")
    print(line)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    args = sys.argv[1:]
    seeds = int(args[args.index("--seeds") + 1]) if "--seeds" in args else 1
    names = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--seeds")]
    for variant in names:
        report(variant, seeds, "--fresh" in args, "--detail" in args, "--dev" in args)
