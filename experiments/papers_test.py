"""Run the readers, as they are, on real papers. There are no labels here:
the script reports only what a program can check.

    python experiments/papers_test.py <folder with .txt papers> [paper ...]
"""

import collections
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from g4geoagent.agent.compare import as_number, check_quotes, numbers_in, uncovered_numbers
from g4geoagent.agent.readers import READERS, read_with_coverage
from g4geoagent.agent.runlog import RunLog

FOLDER = Path(sys.argv[1])
OUT = FOLDER.parent / "readings"
BUILT = {"shape", "position", "material", "count"}


def one(job):
    paper, reader = job
    documents = {paper.name: paper.read_text()}
    log_file = OUT / f"{paper.stem}_{reader}.jsonl"
    log_file.unlink(missing_ok=True)
    log, start = RunLog(log_file), time.time()
    try:
        reading = read_with_coverage(documents, reader, log)
    except Exception as error:
        return paper.stem, reader, None, f"{type(error).__name__}: {str(error)[:150]}"
    (OUT / f"{paper.stem}_{reader}.json").write_text(reading.model_dump_json(indent=1))
    rereads = log.events("reread")
    return paper.stem, reader, {
        "reading": reading, "seconds": time.time() - start,
        "numbers_in_text": len(numbers_in(documents[paper.name])),
        "uncovered_first": sum(rereads[0]["missing"].values()) if rereads else 0,
        "uncovered_end": sum(uncovered_numbers(reading, documents).values()),
        "bad_quotes": check_quotes(reading, documents),
        "categories": collections.Counter(c.category for c in reading.claims),
    }, None


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    wanted = sys.argv[2:]
    papers = [p for p in sorted(FOLDER.glob("*.txt")) if not wanted or p.stem in wanted]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(one, [(p, r) for p in papers for r in READERS]))
    print(f"{'paper':10s} rd  parts claims built not-geo gaps | numbers  uncovered: first  end | bad quotes | sec")
    by_paper = collections.defaultdict(dict)
    for paper, reader, r, error in results:
        if error:
            print(f"{paper:10s} {reader}   FAILED {error}"); continue
        by_paper[paper][reader] = r
        c, reading = r["categories"], r["reading"]
        print(f"{paper:10s} {reader}  {len(reading.parts):5d} {len(reading.claims):6d} {sum(c[k] for k in BUILT):5d} "
              f"{c['not_geometry']:7d} {len(reading.gaps):4d} | {r['numbers_in_text']:7d} {r['uncovered_first']:17d} "
              f"{r['uncovered_end']:4d} | {len(r['bad_quotes']):10d} | {r['seconds']:3.0f}")
    print("\nagreement between the two readers on built values (distinct numbers):")
    for paper, both in by_paper.items():
        if len(both) < 2:
            continue
        sets = [{as_number(c.value) for c in both[r]["reading"].claims
                 if c.category in BUILT and as_number(c.value) is not None} for r in "AB"]
        print(f"  {paper:10s} A has {len(sets[0]):3d}, B has {len(sets[1]):3d}, both have {len(sets[0] & sets[1]):3d}")
