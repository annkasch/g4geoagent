"""Score designs of the knowledge graph on all papers that have hand lists.

    python experiments/graph_bench.py <design> [<design> ...] [--detail] [--fresh] [--papers a,b]

Per design and paper: the readers' raw answers are kept on disk (by the name of the reading
set-up), so a design that changes only checking or merging costs no model call.

Scores, all computed by program against hand lists:
  values     share of the hand-listed construction values (experiments/gold) that are a property in the graph
  relations  share of the hand-listed relations (experiments/gold_relations) that are an edge in the graph
  placed     share of the parts for which the graph says where they are
  joined     share of the parts in the largest group that relations tie together
  agreed     share of properties and relations that both readers found
  dropped    share of the readers' records that the quote check removed
  doubles    pairs of parts whose names suggest the same part twice (fewer is better)
  foreign    parts said to belong to another detector (fewer is better)
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from graph_designs import DESIGNS              # noqa: E402

from g4geoagent.agent import graph as G        # noqa: E402
from g4geoagent.agent.compare import numbers_in  # noqa: E402
from g4geoagent.agent.graph_schemas import Extraction  # noqa: E402
from g4geoagent.agent.runlog import RunLog     # noqa: E402
from g4geoagent.reviewer import look           # noqa: E402

ROOT = Path(__file__).parents[1]
TEXT, PDFS, OUT = ROOT / "runs/papers_test/text", ROOT.parent / "papers", ROOT / "runs/graph_bench"
PAPERS = ["legend", "T2K", "dune", "ice_cube", "super-k"]
NAMES = {"legend": "LEGEND-200", "T2K": "T2K ND280 upgrade", "dune": "DUNE near detector",
         "ice_cube": "IceCube Upgrade multi-PMT optical module (mDOM)", "super-k": "Super-Kamiokande"}
FAMILIES = {"nest": ({"contains", "encloses", "surrounds", "consists_of"}, False),
            "attach": ({"mounted_on", "attached_to"}, True), "any": (None, True)}


def text_of(paper):
    text = (TEXT / f"{paper}.txt").read_text()
    if paper == "super-k":                      # the hand lists cover pages 3 to 7 of this 45-page paper
        text = text[text.find("[page 3]"):text.find("[page 8]")]
    return {f"{paper}.txt": text}


def readings_for(design, paper, fresh, log):
    """The checked readings of one paper under `design`: {reader: Extraction}, and the dropped records."""
    documents, readings, dropped, raw_count = text_of(paper), {}, [], 0

    def raw(reader):
        file = OUT / "readings" / design["reading"] / f"{paper}_{reader}.json"
        if file.exists() and not fresh:
            return Extraction.model_validate_json(file.read_text())
        file.parent.mkdir(parents=True, exist_ok=True)
        answer = G.read_text(documents, reader, log, **design.get("read_options", {}))
        file.write_text(answer.model_dump_json(indent=1))
        return answer

    with ThreadPoolExecutor(2) as pool:
        for reader, extraction in zip("AB", pool.map(raw, "AB")):
            raw_count += len(extraction.parts) + len(extraction.properties) + len(extraction.relations)
            readings[reader], out = G.check(extraction, documents, **design.get("check_options", {}))
            dropped += out
    if design.get("figures"):
        folder = OUT / "figures" / paper
        listing = folder / "construction.json"
        if not listing.exists() or fresh:
            figures = look.extract_figures(PDFS / f"{paper}.pdf", folder)
            if paper == "super-k":
                figures = [f for f in figures if 3 <= f["page"] <= 7]
            kept = look.construction_figures(figures[:12], folder, NAMES[paper], log, most=3)
            listing.write_text(json.dumps(kept, indent=1))
        for figure in json.loads(listing.read_text()):
            file = OUT / "readings" / design["figures"] / f"{paper}_{figure['file']}.json"
            if not file.exists() or fresh:
                file.parent.mkdir(parents=True, exist_ok=True)
                seen = G.read_figure(figure, folder, NAMES[paper], log, **design.get("figure_options", {}))
                file.write_text(seen.model_dump_json(indent=1) if seen else "null")
            if file.read_text() != "null":
                readings[f"figure:{figure['file']}"] = Extraction.model_validate_json(file.read_text())
    return documents, readings, dropped, raw_count


def names_of(node):
    return " ".join([node["name"], *(G.norm(a) for a in node["also_called"])])


def score(graph, paper, dropped, raw_count):
    nodes = {n["name"]: n for n in graph["nodes"]}
    values = [e for e in yaml.safe_load((ROOT / "experiments/gold" / f"{paper}.yaml").read_text()) if not e.get("optional")]

    def has_value(entry):
        wanted = [float(entry["value"])] + ([float(entry["alt"])] if "alt" in entry else [])
        for p in graph["properties"]:
            numbers = [float(p["value"])] if isinstance(p["value"], (int, float)) else numbers_in(str(p["value"]))
            where = f"{p['quote']} {names_of(nodes[p['of']]) if p['of'] in nodes else p['of']} {p['quantity']} {p['unit']}".lower()
            if any(abs(n - w) <= 1e-9 * max(abs(w), 1) for n in numbers for w in wanted) and re.search(entry["key"], where):
                return True
        return False

    relations = yaml.safe_load((ROOT / "experiments/gold_relations" / f"{paper}.yaml").read_text())

    def has_relation(entry):
        allowed, either = FAMILIES.get(entry["family"], ({entry["family"]}, False))
        for r in graph["relations"]:
            s, o = names_of(nodes[r["subject"]]), names_of(nodes[r["object"]])
            if allowed is not None and r["relation"] not in allowed:
                continue
            if (re.search(entry["subject"], s) and re.search(entry["object"], o)) or \
               (either and re.search(entry["subject"], o) and re.search(entry["object"], s)):
                return True
        return False

    def tokens(name):
        return {w for w in name.split("_") if len(w) > 2}
    names = list(nodes)
    doubles = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
               if tokens(a) and tokens(b) and (tokens(a) <= tokens(b) or tokens(b) <= tokens(a))]
    own = set(re.findall(r"[a-z0-9]+", NAMES[paper].lower())) | {paper.lower().replace("_", "")}
    foreign = [n["name"] for n in graph["nodes"]
               if n["about"] and not any(own & set(re.findall(r"[a-z0-9]+", a.lower())) for a in n["about"])]
    main = [n for n in graph["nodes"] if n["detail"] in ("sensitive", "main_structure")]
    with_material = {p["of"] for p in graph["properties"] if p["quantity"] == "material"}
    entries = graph["properties"] + graph["relations"]
    # how much of the graph hangs together: the largest group of parts joined by relations
    linked = {n: {n} for n in nodes}
    for r in graph["relations"]:
        joined = linked[r["subject"]] | linked[r["object"]]
        for n in joined:
            linked[n] = joined
    largest = max((len(g) for g in linked.values()), default=0)
    found_values = [e["what"] for e in values if has_value(e)]
    found_relations = [e["what"] for e in relations if has_relation(e)]
    return {"paper": paper, "nodes": len(nodes), "properties": len(graph["properties"]), "edges": len(graph["relations"]),
            "values": (len(found_values), len(values)), "relations": (len(found_relations), len(relations)),
            "missed_values": [e["what"] for e in values if e["what"] not in found_values],
            "missed_relations": [e["what"] for e in relations if e["what"] not in found_relations],
            "placed": (sum("where it is" not in n["unknown"] for n in graph["nodes"]), len(nodes)),
            "joined": (largest, len(nodes)),
            "material": (sum(n["name"] in with_material for n in main), len(main)),
            "agreed": (sum(e["found_by"] == "both readers" for e in entries), len(entries)),
            "dropped": (len(dropped), raw_count), "doubles": doubles, "foreign": foreign}


def one(job):
    name, paper, fresh = job
    design = DESIGNS[name]
    log = RunLog(OUT / name / f"{paper}.jsonl")
    documents, readings, dropped, raw_count = readings_for(design, paper, fresh, log)
    for step in design.get("after_check", []):               # steps that change the readings, e.g. a cross-check
        readings = step(readings, documents, NAMES[paper], log)
    graph = G.merge(readings, documents, NAMES[paper], **design.get("merge_options", {}))
    if design.get("same_parts"):                             # a model names the parts that appear twice; kept on disk
        file = OUT / "same_parts" / design["same_parts"] / f"{paper}.json"
        if not file.exists() or fresh:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(G.same_parts(graph, log)))
        graph = G.merge(readings, documents, NAMES[paper], same=json.loads(file.read_text()), **design.get("merge_options", {}))
    for step in design.get("after_merge", []):
        graph = step(graph, documents, NAMES[paper], log)
    (OUT / name).mkdir(parents=True, exist_ok=True)
    (OUT / name / f"{paper}.json").write_text(json.dumps(graph, indent=1, default=sorted))
    (OUT / name / f"{paper}.txt").write_text(G.as_text(graph) + "\n")
    return name, score(graph, paper, dropped, raw_count)


if __name__ == "__main__":
    args = sys.argv[1:]
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else PAPERS
    designs = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--papers")]
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(one, [(d, p, "--fresh" in args) for d in designs for p in papers]))
    share = lambda rows, key: sum(r[key][0] for r in rows) / max(sum(r[key][1] for r in rows), 1)
    print(f"{'design':26s} values  relations  placed  joined  agreed  dropped  doubles  parts")
    for design in designs:
        rows = [r for d, r in results if d == design]
        print(f"{design:26s} {share(rows, 'values'):5.0%}  {share(rows, 'relations'):8.0%}  {share(rows, 'placed'):6.0%}  "
              f"{share(rows, 'joined'):5.0%}  {share(rows, 'agreed'):6.0%}  {share(rows, 'dropped'):6.0%}  "
              f"{sum(len(r['doubles']) for r in rows):7d}  {sum(r['nodes'] for r in rows):5d}")
        if "--detail" in args:
            for r in rows:
                print(f"    {r['paper']:9s} values {r['values'][0]}/{r['values'][1]} relations {r['relations'][0]}/{r['relations'][1]} "
                      f"parts {r['nodes']} doubles {len(r['doubles'])} foreign {len(r['foreign'])}")
                print(f"        missed values: {r['missed_values']}")
                print(f"        missed relations: {r['missed_relations']}")
                print(f"        doubles: {r['doubles'][:8]}  foreign: {r['foreign'][:6]}")
