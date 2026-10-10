"""How well do the readers extract the values of a task's documents?

Runs each reader several times on the tasks that have reference/expected_claims.yaml
and compares what it found with those values.

    python experiments/readers_eval.py [repeats]
"""

import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from g4geoagent.agent.compare import as_number, check_quotes, uncovered_numbers
from g4geoagent.agent.readers import READERS, load_documents, read, read_with_coverage
from g4geoagent.agent.runlog import RunLog

ROOT = Path(__file__).parents[1]
OUT = ROOT / "runs" / "readers_eval"
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
REREAD = "reread" in sys.argv        # send uncovered numbers back to the reader


def score(reading, expected, documents):
    """Compare a reading with the expected values. Returns a dict of counts and lists."""
    claims = [(as_number(c.value), c.category != "not_geometry", c) for c in reading.claims]
    used, right, wrong_category, missed = set(), 0, [], []
    for want in expected:
        same = [i for i, (v, _, _) in enumerate(claims)
                if i not in used and v is not None and math.isclose(v, float(want["value"]), rel_tol=1e-9, abs_tol=1e-12)]
        exact = [i for i in same if claims[i][1] == want["built"]]
        if exact:
            used.add(exact[0]); right += 1
        elif same:
            used.add(same[0]); wrong_category.append(want["what"])
        else:
            missed.append(want["what"])
    extra = [f"{c.quantity}={c.value}" for i, (v, _, c) in enumerate(claims) if v is not None and i not in used]
    return {"right": right, "wrong_category": wrong_category, "missed": missed, "extra": extra,
            "bad_quotes": [f"{c.quantity}: {why}" for c, why in check_quotes(reading, documents)],
            "uncovered": uncovered_numbers(reading, documents), "gaps": len(reading.gaps)}


def one(job):
    task, reader, i = job
    documents = load_documents(task / "docs")
    expected = yaml.safe_load((task / "reference" / "expected_claims.yaml").read_text())
    log = RunLog(OUT / f"{task.name}_{reader}_{i}.jsonl")
    try:
        reading = (read_with_coverage if REREAD else read)(documents, reader, log)
    except Exception as error:
        return task.name, reader, i, len(expected), None, f"{type(error).__name__}: {str(error)[:120]}"
    (OUT / f"{task.name}_{reader}_{i}.json").write_text(reading.model_dump_json(indent=1))
    return task.name, reader, i, len(expected), score(reading, expected, documents), None


if __name__ == "__main__":
    tasks = sorted(p.parents[1] for p in (ROOT / "tasks").glob("*/reference/expected_claims.yaml"))
    jobs = [(task, reader, i) for task in tasks for reader in READERS for i in range(REPEATS)]
    for old in OUT.glob("*.json*"):
        old.unlink()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, jobs))
    print(f"{'task':14s} reader run  right  wrong-cat  missed  extra  bad-quotes  uncovered")
    for task, reader, i, n, s, error in results:
        if error:
            print(f"{task:14s} {reader:6s} {i}    FAILED {error}"); continue
        print(f"{task:14s} {reader} ({READERS[reader][0][4:]:12s}) {i}  {s['right']:2d}/{n}  {len(s['wrong_category']):6d}  "
              f"{len(s['missed']):6d}  {len(s['extra']):5d}  {len(s['bad_quotes']):8d}  {sum(s['uncovered'].values()):8d}")
    print()
    for task, reader, i, n, s, error in results:
        if s and (s["wrong_category"] or s["missed"] or s["extra"] or s["bad_quotes"]):
            print(f"{task} {reader}{i}: wrong category {s['wrong_category']} | missed {s['missed']} | "
                  f"extra {s['extra']} | bad quotes {s['bad_quotes']}")
