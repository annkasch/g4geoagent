"""Score the two steps "claims" and "detector graph built by a model" on the five papers with hand lists.

    python experiments/claims_graph_bench.py <variant> [<variant> ...] [--detail] [--fresh] [--papers a,b]

The claims come from the readings that experiments/graph_bench.py keeps on disk (design 14: two passes per
reader, quote check, missed numbers, cross-check with two votes, figures), so the claim step costs no model
call here. Each variant then builds the graph from the same claims.

Scores: as in graph_bench.py (values and relations of the hand lists present in the graph), plus what the
program checks found: entries it had to take out because no claim supports them, claims the model left
unaccounted, relations the model inferred, and how many repair rounds were needed.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import graph_bench as B                         # noqa: E402
from graph_designs import DESIGNS               # noqa: E402

from g4geoagent.agent import claims as C        # noqa: E402
from g4geoagent.agent import detector_graph as D  # noqa: E402
from g4geoagent.agent import graph as G         # noqa: E402
from g4geoagent.agent.runlog import RunLog      # noqa: E402

OUT = B.ROOT / "runs/claims_graph"
VARIANTS = {
    "c01_one_call": {},                              # one model builds the graph, the program checks, up to 3 repairs
    "c02_reviewed": {"with_review": True},           # and a second model reviews the graph against the claims
    # 3: the same fact found by both readers under two names for the part is one claim (claims "v2");
    #    fixed reasons for setting a claim aside, checked by program; materials are properties
    "c03_fixed_reasons": {"claims": "v2"},
    # 4: variant 3 in two stages: first the parts and how they are arranged, then the values in batches
    "c04_two_stages": {"claims": "v2", "stages": 2},
    # 5: variant 4, and (a) the tree must follow the relations that claims state (surrounds, encloses, contains);
    #    (b) a built value is never "not geometry"; (c) a program keeps each value once per part, with the wording,
    #    unit and each/total of its claim, and copies shapes and features from the cited claims; (d) a part said to
    #    be outside another is not put inside it; (e) values in batches of 40, in parallel
    "c05_strict_tidy": {"claims": "v2", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40}},
    # 6: variant 5, with claims whose numbers were checked sentence by sentence (claims "v3"), and a tree with one
    #    root: only the detector as a whole or the outermost part is inside 'world', and "A consists of B" puts B inside A
    "c06_one_root": {"claims": "v3", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40, "one_root": True}},
    # 7: variant 6, and a relation claim that says where something is (at the bottom of, attached to, next to) may
    #    not be set aside as "same as" a claim of another kind; text values such as "about 6 t" become numbers
    "c07_place_relations": {"claims": "v3", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40, "one_root": True}},
    # 8: variant 7, and a second model checks value by value, against its sentence, that it sits on the right part
    "c08_values_reviewed": {"claims": "v3", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40, "one_root": True, "review": True}},
    # 9: variant 7, and a claim that says where a part is always becomes an edge: where the model used it only to
    #    decide what is inside what, the program adds the edge
    "c09_place_edges": {"claims": "v3", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40, "one_root": True}},
    # 10: variant 9, and what a claim states stays in the graph as stated: where the model kept only a value it
    #     worked out, or dropped one of two values that disagree, the program puts the stated value back and notes it
    "c10_keep_stated": {"claims": "v3", "stages": 2, "options": {"strict": True, "parallel": True, "batch": 40, "one_root": True, "keep_stated": True}},
}


def claims_of(paper, fresh=False, version="v1"):
    """The claims of a paper, from the kept readings of design 14."""
    folder = OUT / ("claims" if version == "v1" else f"claims_{version}") / paper
    if (folder / "claims.jsonl").exists() and not fresh:
        return C.load(folder)
    design, log = DESIGNS["g14_tidy"], RunLog(folder / "log.jsonl")
    documents, readings, dropped, _ = B.readings_for(design, paper, False, log)
    file = B.OUT / "coverage" / design["coverage"] / f"{paper}.json"
    readings["A"].properties += [G.Property.model_validate(p) for p in json.loads(file.read_text())]
    if version == "v3":                         # a second pass for numbers not covered in their own sentence, and number words
        file = B.OUT / "coverage" / "per_sentence" / f"{paper}.json"
        if not file.exists() or fresh:
            file.parent.mkdir(parents=True, exist_ok=True)
            more = G.coverage_pass(readings, documents, B.NAMES[paper], log, per_sentence=True)
            file.write_text(json.dumps([p.model_dump() for p in more], indent=1))
        readings["A"].properties += [G.Property.model_validate(p) for p in json.loads(file.read_text())]
    file = B.OUT / "cross_check" / design["cross_check"] / f"{paper}.json"
    known = json.loads(file.read_text()) if file.exists() else {}
    readings, disputed = G.cross_check(readings, documents, B.NAMES[paper], log, known, **design["cross_options"])
    claims = C.ledger(readings, [{"reader": "", **d} for d in dropped], disputed, documents, join_same_facts=version != "v1")
    C.save(claims, folder)
    return claims


def one(job):
    variant, paper, fresh = job
    folder = OUT / variant / paper
    claims = claims_of(paper, version=VARIANTS[variant].get("claims", "v1"))
    accepted = [c for c in claims if c.status == "accepted"]
    if not (folder / "detector_graph.json").exists() or fresh:
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if VARIANTS[variant].get("stages") == 2:
                graph, record = D.build_in_two(claims, B.NAMES[paper], RunLog(folder / "log.jsonl"), **VARIANTS[variant].get("options", {}))
            else:
                graph, record = D.build(claims, B.NAMES[paper], RunLog(folder / "log.jsonl"),
                                        with_review=VARIANTS[variant].get("with_review", False))
            data = D.to_dict(graph, accepted, B.NAMES[paper], record)
        except Exception as error:
            data = {"detector": B.NAMES[paper], "nodes": [], "properties": [], "relations": [], "set_aside": [],
                    "checks": {"rounds": [[f"{type(error).__name__}: {str(error)[:200]}"]], "review": [], "removed": [], "unaccounted": []}}
        (folder / "detector_graph.json").write_text(json.dumps(data, indent=1))
        (folder / "detector_graph.txt").write_text(D.as_text(data) + "\n")
    data = json.loads((folder / "detector_graph.json").read_text())
    for n in data["nodes"]:
        n.setdefault("about", [B.NAMES[paper]])
    checks = data["checks"]
    result = B.score(data, paper, [], 1) if data["nodes"] else {
        "paper": paper, "nodes": 0, "properties": 0, "edges": 0, "values": (0, 1), "relations": (0, 1), "missed_values": [],
        "missed_relations": [], "placed": (0, 1), "joined": (0, 1), "agreed": (0, 1), "dropped": (0, 1), "doubles": [], "foreign": []}
    return variant, {**result, "claims": len(accepted), "removed": len(checks.get("removed", [])),
                     "unaccounted": len(checks.get("unaccounted", [])), "repairs": max(len(checks.get("rounds", [])) - 1, 0),
                     "first_problems": len(checks["rounds"][0]) if checks.get("rounds") else 0,
                     "objections": len(checks.get("review", [])),
                     "inferred": sum(bool(r.get("inferred")) for r in data["relations"]),
                     "derived": sum(bool(p.get("derived")) for p in data["properties"]),
                     "set_aside": len(data.get("set_aside", [])),
                     "roots": sum(n["inside"] == "world" for n in data["nodes"])}


if __name__ == "__main__":
    args = sys.argv[1:]
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else B.PAPERS
    variants = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--papers")]
    for version in {VARIANTS[v].get("claims", "v1") for v in variants}:
        for paper in papers:
            claims_of(paper, "--fresh-claims" in args, version)
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(one, [(v, p, "--fresh" in args) for v in variants for p in papers]))
    share = lambda rows, key: sum(r[key][0] for r in rows) / max(sum(r[key][1] for r in rows), 1)
    total = lambda rows, key: sum(r[key] for r in rows)
    print(f"{'variant':16s} values  relations  joined  roots  parts  claims  set aside  unaccounted  taken out  inferred  derived  repairs")
    for variant in variants:
        rows = [r for v, r in results if v == variant]
        print(f"{variant:16s} {share(rows, 'values'):5.0%}  {share(rows, 'relations'):8.0%}  {share(rows, 'joined'):5.0%}  "
              f"{total(rows, 'roots'):5d}  {total(rows, 'nodes'):5d}  {total(rows, 'claims'):6d}  {total(rows, 'set_aside'):9d}  "
              f"{total(rows, 'unaccounted'):11d}  {total(rows, 'removed'):9d}  {total(rows, 'inferred'):8d}  {total(rows, 'derived'):7d}  {total(rows, 'repairs'):7d}")
        if "--detail" in args:
            for r in rows:
                print(f"    {r['paper']:9s} values {r['values'][0]}/{r['values'][1]} relations {r['relations'][0]}/{r['relations'][1]} "
                      f"parts {r['nodes']} of {r['claims']} claims; first check: {r['first_problems']} problems; objections {r['objections']}")
                print(f"        missed values: {r['missed_values']}")
                print(f"        missed relations: {r['missed_relations']}")
