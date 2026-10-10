"""Reading papers: the construction-only prompt alone ("before") against the same prompt
with reading in pieces for long papers and one round of verdicts on numbers left out
near the claims ("now").

    python experiments/prompt_test.py
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from g4geoagent.agent.compare import check_quotes, claim_numbers, uncovered_near_claims
from g4geoagent.agent.readers import READERS, read_paper
from g4geoagent.agent.runlog import RunLog
from g4geoagent.agent.schemas import Reading

ROOT = Path(__file__).parents[1] / "runs" / "papers_test"
OLD, NEW = ROOT / "readings_paper_prompt", ROOT / "readings_improved"
PAPERS = ["legend", "T2K", "dune", "hyper-k", "ice_cube", "super-k"]
# Construction values in the LEGEND paper, listed by hand from its section 2.1 and 2.2:
# tank 10 m x 8 m, 590 m3, 66 PMTs, cryostat 4 m, 64 m3, reflector 1374 mm x 3 m, 6 t,
# 12 strings, 200 kg, 90% enrichment
LEGEND_VALUES = [10, 8, 590, 66, 4, 64, 1374, 3, 6, 12, 200, 90]


def built(reading):
    return {n for c in reading.claims if c.category != "not_geometry" for n in claim_numbers(c)}


def one(job):
    paper, reader = job
    documents = {f"{paper}.txt": (ROOT / "text" / f"{paper}.txt").read_text()}
    start = time.time()
    try:
        reading = read_paper(documents, reader, RunLog(NEW / f"{paper}_{reader}.jsonl"))
    except Exception as error:
        return paper, reader, None, f"{type(error).__name__}: {str(error)[:100]}", 0, documents
    (NEW / f"{paper}_{reader}.json").write_text(reading.model_dump_json(indent=1))
    return paper, reader, reading, None, time.time() - start, documents


def row(label, reading, documents, seconds=None):
    n = len(reading.claims)
    noise = sum(c.category == "not_geometry" for c in reading.claims)
    bad = len(check_quotes(reading, documents))
    took = f"{seconds:4.0f} s" if seconds else "      "
    near = len(uncovered_near_claims(reading, documents))
    return (f"{label:9s} {n:4d} claims, {n - noise:3d} geometry, {noise:3d} not geometry, "
            f"{bad:3d} quotes failing, {near:3d} numbers without claim near claims {took}")


if __name__ == "__main__":
    NEW.mkdir(exist_ok=True)
    for old in NEW.glob("*.json*"):
        old.unlink()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(one, [(p, r) for p in PAPERS for r in READERS]))
    new = {}
    for paper, reader, reading, error, seconds, documents in results:
        print(f"--- {paper}, reader {reader}")
        before = OLD / f"{paper}_{reader}.json"
        if before.exists():
            old_reading = Reading.model_validate_json(before.read_text())
            print("  ", row("before:", old_reading, documents))
        if error:
            print("   now:      FAILED", error); continue
        new[paper, reader] = reading
        print("  ", row("now:", reading, documents, seconds))
        if before.exists():
            kept, was = built(reading) & built(old_reading), built(old_reading)
            print(f"   geometry values from before that are still found: {len(kept)} of {len(was)}; "
                  f"new ones: {len(built(reading) - was)}")
        if paper == "legend":
            for label, r in (("before", old_reading), ("now", reading)):
                found = [v for v in LEGEND_VALUES if v in built(r)]
                print(f"   hand-listed LEGEND values found {label}: {len(found)} of {len(LEGEND_VALUES)}"
                      f" (missing {[v for v in LEGEND_VALUES if v not in found]})")
    print("\nagreement between the readers on geometry values, new prompt:")
    for paper in PAPERS:
        if (paper, "A") in new and (paper, "B") in new:
            a, b = built(new[paper, "A"]), built(new[paper, "B"])
            print(f"  {paper:9s} A has {len(a):3d}, B has {len(b):3d}, both have {len(a & b):3d}")
