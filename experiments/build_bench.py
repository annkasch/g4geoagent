"""Score variants of the Build box: build from fixed agreed claims, measure against those claims.

    python experiments/build_bench.py <variant> [<variant> ...] [--seeds N] [--papers a,b] [--fresh]

The claims are the saved agreed readings of experiments/reader_bench.py, so reading
plays no part in the score. Per run: does the geometry load in Geant4, how many of
the claims that describe the construction are met in it, and how many of the
hand-listed facts of the paper (experiments/gold) are met.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from build_variants import VARIANTS            # noqa: E402
from reader_bench import DEV, GOLD, matches    # noqa: E402

from g4geoagent import pipeline                # noqa: E402
from g4geoagent.agent.evidence import Evidence  # noqa: E402
from g4geoagent.agent.runlog import RunLog     # noqa: E402
from g4geoagent.agent.schemas import Reading   # noqa: E402

ROOT = Path(__file__).parents[1]
TEXT, READINGS, OUT = ROOT / "runs/papers_test/text", ROOT / "runs/reader_bench/agreed/seed0", ROOT / "runs/build_bench"
NAMES = {"legend": "LEGEND-200", "T2K": "T2K ND280 upgrade", "dune": "DUNE near detector",
         "ice_cube": "IceCube Upgrade multi-PMT optical module (mDOM)", "super-k": "Super-Kamiokande"}


def one(job):
    variant, paper, seed, fresh = job
    folder = OUT / variant / paper / f"seed{seed}"
    result_file = folder / "result.json"
    if result_file.exists() and not fresh:
        return json.loads(result_file.read_text())
    if folder.exists():
        for old in folder.rglob("*"):
            old.unlink() if old.is_file() else None
    log = RunLog(folder / "log.jsonl")
    state = pipeline.State(folder=folder, name=NAMES[paper], log=log, evidence=Evidence(folder / "evidence", log), seed=seed)
    state.evidence.add_starting(TEXT / f"{paper}.txt")
    reading = Reading.model_validate_json((READINGS / f"{paper}.json").read_text())
    state.parts = {p.name: p for p in reading.parts}
    for claim in reading.claims:
        key = f"C{len(state.claims) + 1}"
        state.claims[key], state.origin[key] = claim, claim.source
    state.round = 1
    VARIANTS[variant](state)
    log.enter(("teams",))
    try:
        pipeline.build(state)
        error = ""
    except Exception as failure:
        error = f"{type(failure).__name__}: {str(failure)[:200]}"
    best = state.candidate
    gold = [e for e in yaml.safe_load((GOLD / f"{paper}.yaml").read_text()) if not e.get("optional")]
    rows = {r["id"]: r for r in best["rows"]} if best else {}
    facts = sum(any(matches(c, e) and rows.get(k, {}).get("status") == "met" for k, c in state.claims.items()) for e in gold)
    attempts = [e for e in log.events("build_attempt")]
    result = {"variant": variant, "paper": paper, "seed": seed, "valid": bool(best), "error": error,
              "attempts": len(attempts), "claims": len(state.built_claims()), "facts": facts, "facts_required": len(gold),
              **(best["summary"] if best else {"met": 0, "not met": 0, "not measurable": 0, "not shown": 0}),
              "volumes": len(best["report"].get("parts", [])) - 1 if best else 0,
              "problems": [a.get("problem", "")[-300:] for a in attempts if a["outcome"] == "problem"]}
    result_file.write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    seeds = int(args[args.index("--seeds") + 1]) if "--seeds" in args else 2
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else DEV
    skip = {args[i + 1] for i, a in enumerate(args) if a in ("--seeds", "--papers")}
    variants = [a for a in args if not a.startswith("--") and a not in skip]
    jobs = [(v, p, s, "--fresh" in args) for v in variants for p in papers for s in range(seeds)]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(one, jobs))
    print(f"{'variant':22s} valid  claims met  facts met  attempts  volumes")
    for variant in variants:
        rs = [r for r in results if r["variant"] == variant]
        print(f"{variant:22s} {sum(r['valid'] for r in rs)}/{len(rs)}   "
              f"{sum(r['met'] for r in rs) / max(sum(r['claims'] for r in rs), 1):9.0%}  "
              f"{sum(r['facts'] for r in rs) / max(sum(r['facts_required'] for r in rs), 1):8.0%}  "
              f"{sum(r['attempts'] for r in rs) / len(rs):8.1f}  {sum(r['volumes'] for r in rs) / len(rs):7.0f}")
        for r in rs:
            print(f"    {r['paper']:9s} seed {r['seed']}: valid {r['valid']!s:5s} met {r['met']:2d} not met {r['not met']:2d} "
                  f"not shown {r['not shown']:2d} of {r['claims']:2d}; facts {r['facts']}/{r['facts_required']}; {r['attempts']} attempts {r['error']}")
