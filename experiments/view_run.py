"""Make the geometry view of the finished graphs of a run, and score it against the hand lists.

    python experiments/view_run.py <run name> [--papers a,b] [--workers 5]

For each paper reads runs/papers20/<paper>/<run>/detector_graph.json, writes geometry_view.json and geometry_view.txt
beside it, and prints a table: parts in the graph and in the view, and the hand-listed values and relations that are
in the graph and still in the view (a value counts if its part is kept, a relation if both its parts are kept).
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

import first_run as F                                  # noqa: E402
import graph_bench as B                                # noqa: E402
from g4geoagent.agent import detector_graph as D       # noqa: E402
from g4geoagent.agent.runlog import RunLog             # noqa: E402


def one(paper, name):
    folder = F.HOME / paper / name
    data = json.loads((folder / "detector_graph.json").read_text())
    if not (folder / "geometry_view.json").exists():
        view = D.geometry_view(data, F.detector_name(paper), RunLog(folder / "log.jsonl"))
        (folder / "geometry_view.json").write_text(json.dumps(view, indent=1))
        (folder / "geometry_view.txt").write_text(D.view_as_text(data, view) + "\n")
    view = json.loads((folder / "geometry_view.json").read_text())
    keep = set(view["keep"])
    B.NAMES[paper] = F.detector_name(paper)
    for n in data["nodes"]:
        n.setdefault("about", [B.NAMES[paper]])
    shown = {**data, "nodes": [n for n in data["nodes"] if n["name"] in keep],
             "properties": [p for p in data["properties"] if p["of"] in keep],
             "relations": [r for r in data["relations"] if r["subject"] in keep and r["object"] in keep]}
    full, kept = B.score(data, paper, [], 1), B.score(shown, paper, [], 1)
    values, relations = F.hand_lists(paper)
    return {"paper": paper, "parts": len(data["nodes"]), "kept": len(keep), "collapsed": len(view["collapse"]),
            "dropped": len(view["drop"]), "values": len(values), "relations": len(relations),
            "values_graph": len(values) - len(full["missed_values"]), "values_view": len(values) - len(kept["missed_values"]),
            "relations_graph": len(relations) - len(full["missed_relations"]), "relations_view": len(relations) - len(kept["missed_relations"]),
            "lost_values": sorted(set(kept["missed_values"]) - set(full["missed_values"])),
            "lost_relations": sorted(set(kept["missed_relations"]) - set(full["missed_relations"]))}


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[0]
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else [p["name"] for p in F.PAPERS]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 5
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(lambda p: one(p, name), papers))
    split = {p["name"]: p["split"] for p in F.PAPERS}
    (F.HOME / f"{name}_view.json").write_text(json.dumps(rows, indent=1))
    print(f"{'paper':20s} {'split':11s} {'parts':>5s} {'kept':>5s} {'coll.':>5s} {'drop':>5s}   values graph->view   relations graph->view")
    for r in rows:
        print(f"{r['paper']:20s} {split[r['paper']]:11s} {r['parts']:5d} {r['kept']:5d} {r['collapsed']:5d} {r['dropped']:5d}   "
              f"{r['values_graph']:3d} -> {r['values_view']:3d} of {r['values']:3d}   {r['relations_graph']:3d} -> {r['relations_view']:3d} of {r['relations']:3d}")
    t = {k: sum(r[k] for r in rows) for k in ("parts", "kept", "collapsed", "dropped", "values", "values_graph", "values_view", "relations", "relations_graph", "relations_view")}
    print(f"{'TOTAL':32s} {t['parts']:5d} {t['kept']:5d} {t['collapsed']:5d} {t['dropped']:5d}   {t['values_graph']:3d} -> {t['values_view']:3d} of {t['values']:3d}   "
          f"{t['relations_graph']:3d} -> {t['relations_view']:3d} of {t['relations']:3d}")
