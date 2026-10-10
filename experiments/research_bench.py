"""Score variants of the Research box: can it find a paper that states a value we pretend is missing?

    python experiments/research_bench.py <variant> [<variant> ...] [--papers a,b] [--fresh] [--detail]

For every hand-listed fact of a paper (experiments/gold), Research is asked for that
fact as if the starting paper did not give it. The starting paper itself is never
offered again. A search counts as found when the saved text has a sentence that
states the value together with the fact's key word. This checks the search and the
choice of paper, not the reading of it, and takes seconds per fact.
"""

import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from build_bench import NAMES                  # noqa: E402
from reader_bench import DEV, GOLD             # noqa: E402
from research_variants import VARIANTS         # noqa: E402

from g4geoagent.agent.compare import numbers_in, sentences   # noqa: E402
from g4geoagent.agent.evidence import Evidence  # noqa: E402
from g4geoagent.agent.runlog import RunLog     # noqa: E402

ROOT = Path(__file__).parents[1]
TEXT, OUT = ROOT / "runs/papers_test/text", ROOT / "runs/research_bench"


def states(text, entry):
    """Does `text` have a sentence with the value of `entry` and its key word?"""
    wanted = [float(entry["value"])] + ([float(entry["alt"])] if "alt" in entry else [])
    for sentence in sentences(text):
        if re.search(entry["key"], sentence.lower()) and any(n in wanted for n in numbers_in(sentence)):
            return sentence[:200]
    return ""


def one(job):
    variant, paper, index, entry, fresh = job
    folder = OUT / variant / paper / f"fact{index:02d}"
    result_file = folder / "result.json"
    if result_file.exists() and not fresh:
        return json.loads(result_file.read_text())
    shutil.rmtree(folder, ignore_errors=True)
    log = RunLog(folder / "log.jsonl")
    evidence = Evidence(folder / "evidence", log)
    evidence.add_starting(TEXT / f"{paper}.txt")
    what = re.sub(r"\s*\(.*?\)", "", entry["what"])          # "water tank diameter (m)" -> "water tank diameter"
    try:
        found = VARIANTS[variant](evidence, NAMES[paper], what, log)
    except Exception as error:
        found = {"file": None, "outcome": f"{type(error).__name__}: {str(error)[:200]}", "candidates": 0}
    files = found.get("files") or ([found["file"]] if found.get("file") else [])
    sentence = next((s for s in (states((evidence.folder / f).read_text(), entry) for f in files) if s), "")
    result = {"variant": variant, "paper": paper, "what": entry["what"], "saved": bool(files), "found": bool(sentence),
              "sentence": sentence, "title": found.get("title", ""), "outcome": found.get("outcome", ""),
              "candidates": found.get("candidates", 0), "llm_calls": len(log.events("llm_call")),
              "fetches": len(log.events("fetch"))}
    for pdf in (folder / "evidence").glob("*.pdf"):          # the text is kept, the PDFs would fill the disk
        pdf.unlink()
    result_file.write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else DEV
    variants = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--papers")]
    jobs = [(v, p, i, e, "--fresh" in args) for v in variants for p in papers
            for i, e in enumerate(yaml.safe_load((GOLD / f"{p}.yaml").read_text())) if not e.get("optional")]
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, jobs))
    print(f"{'variant':24s} found  paper saved  model calls  fetches")
    for variant in variants:
        rs = [r for r in results if r["variant"] == variant]
        print(f"{variant:24s} {sum(r['found'] for r in rs):2d}/{len(rs)}  {sum(r['saved'] for r in rs):5d}/{len(rs)}  "
              f"{sum(r['llm_calls'] for r in rs) / len(rs):10.1f}  {sum(r['fetches'] for r in rs) / len(rs):7.1f}")
        if "--detail" in args:
            for r in rs:
                print(f"    {r['paper']:7s} {'FOUND' if r['found'] else '  -  '} {r['what'][:34]:34s} | {r['title'][:60]} | {r['outcome'][:70]}")
