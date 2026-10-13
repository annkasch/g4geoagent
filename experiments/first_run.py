"""Run the steps from the text of a paper to the detector graph on the 20 further papers, and compare with the hand lists.

    python experiments/first_run.py [run name] [--papers a,b] [--workers 4] [--compare-only] [--free]

For every paper in experiments/papers20.yaml this runs the claim step (g4geoagent/agent/claims.py) and the graph
step (g4geoagent/agent/detector_graph.py) as they are, on the text and figures that step 1 wrote to
runs/papers20/<paper>/step1, and writes into runs/papers20/<paper>/<run name>/ :

    claims.jsonl, claims.txt            every claim, with its source and checks
    detector_graph.json, .txt           the graph
    log.jsonl                           every model call
    compare.json, compare.txt           each entry of the hand list: found or missed, among the claims and in the
                                        graph, with the claims that match it; and the claims that are on no list

and one table of totals for all papers in runs/papers20/<run name>_summary.txt and .json. The table shows totals
only, so that it can be read for test papers without seeing which entries were missed.

A hand-list value is found if an accepted claim (or a value in the graph) has its number and one of its key words.
A hand-list relation is found if an accepted relation claim (or an edge of the graph) joins parts whose names match
its two ends: for 'nest' a contains / encloses / surrounds / consists_of from the first to the second, for 'attach'
a mounted_on / attached_to either way round, for 'any' any relation either way round.
The lists are not complete: a claim that is on no list is not judged, it may well be right.
"""

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

import graph_bench as B                                # noqa: E402
from g4geoagent.agent import claims as C               # noqa: E402
from g4geoagent.agent import detector_graph as D       # noqa: E402
from g4geoagent.agent import statements as S           # noqa: E402
from g4geoagent.agent.runlog import RunLog             # noqa: E402

HOME = ROOT / "runs/papers20"
READER = "free" if "--free" in sys.argv else "form"      # --free: the readers of statements.py instead of claims.py
PAPERS = yaml.safe_load((ROOT / "experiments/papers20.yaml").read_text())


def hand_lists(paper):
    values = yaml.safe_load((ROOT / "experiments/gold" / f"{paper}.yaml").read_text())
    relations = yaml.safe_load((ROOT / "experiments/gold_relations" / f"{paper}.yaml").read_text())
    return [e for e in values if not e.get("optional")], relations


def detector_name(paper):
    line = next(l for l in (ROOT / "experiments/gold" / f"{paper}.yaml").read_text().splitlines() if l.startswith("# detector:"))
    return line[len("# detector:"):].split("(the main detector only")[0].strip()


def value_matches(claim, entry):
    wanted = [float(entry["value"])] + ([float(entry["alt"])] if "alt" in entry else [])
    numbers = [float(claim.value)] if isinstance(claim.value, (int, float)) else B.numbers_in(str(claim.value))
    if not any(abs(n - w) <= 1e-9 * max(abs(w), 1) for n in numbers for w in wanted):
        return False
    where = f"{claim.quote} {claim.statement} {claim.subject} {claim.quantity} {claim.which} {claim.unit}".lower()
    return re.search(entry["key"], where) is not None


def relation_matches(claim, entry):
    allowed, either = B.FAMILIES.get(entry["family"], ({entry["family"]}, False))
    if claim.statement and not claim.relation:
        # a statement of the free reader about several parts, with no fixed kind of relation: it can stand for an
        # entry that needs no containment, if one of its parts matches each end
        names = [p.lower() for p in claim.parts]
        return entry["family"] in ("any", "attach") and any(
            re.search(entry["subject"], a) and re.search(entry["object"], b) for a in names for b in names if a != b)
    if allowed is not None and claim.relation not in allowed:
        return False
    s, o = claim.subject.lower(), claim.object.lower()
    return bool((re.search(entry["subject"], s) and re.search(entry["object"], o)) or
                (either and re.search(entry["subject"], o) and re.search(entry["object"], s)))


def run(paper, name):
    """The claim step and the graph step of one paper. What exists already is kept."""
    step1, folder = HOME / paper / "step1", HOME / paper / name
    folder.mkdir(parents=True, exist_ok=True)
    log, detector, record = RunLog(folder / "log.jsonl"), detector_name(paper), {}
    if not (folder / "claims.jsonl").exists():
        seen, figures = set(), []
        for line in (step1 / "figures" / "all_figures.jsonl").read_text().splitlines():
            figure = json.loads(line)
            if figure["file"] not in seen:
                seen.add(figure["file"])
                figures.append(figure)
        started = time.time()
        try:
            step = S.claim_step if READER == "free" else C.claim_step
            step(folder, [step1 / f"{paper}.txt"], detector=detector, log=log, figures=(figures, step1 / "figures"))
        except Exception as error:
            record["claim_step_error"] = f"{type(error).__name__}: {str(error)[:300]}"
        record["claim_step_seconds"] = round(time.time() - started)
    if (folder / "claims.jsonl").exists() and not (folder / "detector_graph.json").exists():
        started = time.time()
        try:
            D.graph_step(folder, detector, log)
        except Exception as error:
            record["graph_step_error"] = f"{type(error).__name__}: {str(error)[:300]}"
        record["graph_step_seconds"] = round(time.time() - started)
    if record:
        old = json.loads((folder / "run.json").read_text()) if (folder / "run.json").exists() else {}
        (folder / "run.json").write_text(json.dumps({**old, **record}, indent=1))
    return compare(paper, name)


def compare(paper, name):
    """Hand list against the claims and against the graph of one paper. Writes compare.json and compare.txt."""
    folder = HOME / paper / name
    values, relations = hand_lists(paper)
    record = json.loads((folder / "run.json").read_text()) if (folder / "run.json").exists() else {}
    claims = C.load(folder) if (folder / "claims.jsonl").exists() else []
    accepted = [c for c in claims if c.status == "accepted"]
    graph = json.loads((folder / "detector_graph.json").read_text()) if (folder / "detector_graph.json").exists() else None
    in_graph = {"values": set(), "relations": set()}
    graph_numbers = {}
    if graph and graph["nodes"]:
        B.NAMES[paper] = detector_name(paper)
        for node in graph["nodes"]:
            node.setdefault("about", [B.NAMES[paper]])
        result = B.score(graph, paper, [], 1)
        in_graph = {"values": {e["what"] for e in values} - set(result["missed_values"]),
                    "relations": {e["what"] for e in relations} - set(result["missed_relations"])}
        graph_numbers = {"nodes": result["nodes"], "graph_values": result["properties"], "edges": result["edges"],
                         "roots": sum(n["inside"] == "world" for n in graph["nodes"]),
                         "removed": len(graph["checks"].get("removed", [])), "unaccounted": len(graph["checks"].get("unaccounted", []))}
    used, rows = set(), {"values": [], "relations": []}
    for kind, entries, test in (("values", values, value_matches), ("relations", relations, relation_matches)):
        wanted = "value" if kind == "values" else "relation"
        for entry in entries:
            hits = [c for c in accepted if c.kind == wanted and test(c, entry)]
            if kind == "values":                    # a count that a relation carries: "module consists of bar (x192)"
                hits += [c for c in accepted if c.kind == "relation" and c.count is not None
                         and abs(c.count - float(entry["value"])) < 1e-9
                         and re.search(entry["key"], f"{c.quote} {c.subject} {c.object}".lower())]
            near = [c for c in claims if c.status != "accepted" and c.kind == wanted and test(c, entry)]
            used.update(c.id for c in hits)
            rows[kind].append({"entry": entry, "among_claims": bool(hits), "in_graph": entry["what"] in in_graph[kind],
                               "claims": [c.line() for c in hits],
                               "taken_out": [f"{c.line()} | {c.status}: {c.checks[-1]}" for c in near]})
    extra = [c for c in accepted if c.kind in ("value", "relation") and c.id not in used]
    totals = {"paper": paper, "detector": detector_name(paper), **record,
              "claims_accepted": len(accepted), "claims_disputed": sum(c.status == "disputed" for c in claims),
              "claims_dropped": sum(c.status == "dropped" for c in claims), **graph_numbers,
              "values_listed": len(values), "values_among_claims": sum(r["among_claims"] for r in rows["values"]),
              "values_in_graph": sum(r["in_graph"] for r in rows["values"]),
              "relations_listed": len(relations), "relations_among_claims": sum(r["among_claims"] for r in rows["relations"]),
              "relations_in_graph": sum(r["in_graph"] for r in rows["relations"]),
              "claims_on_no_list": len(extra)}
    (folder / "compare.json").write_text(json.dumps({"totals": totals, **rows, "claims_on_no_list": [c.line() for c in extra]}, indent=1))
    lines = [f"{paper}: {totals['detector']}", ""]
    for kind in ("values", "relations"):
        lines += [f"--- hand-listed {kind}: {totals[f'{kind}_among_claims']} of {totals[f'{kind}_listed']} among the claims, "
                  f"{totals[f'{kind}_in_graph']} in the graph"]
        for r in rows[kind]:
            e = r["entry"]
            what = f"{e['value']}  {e['what']}" if kind == "values" else f"[{e['family']}] {e['what']}"
            state = ("found" if r["among_claims"] and r["in_graph"] else "claims only" if r["among_claims"]
                     else "graph only" if r["in_graph"] else "MISSED")
            lines.append(f"{state:12s} {what}")
            lines += [f"                 {c}" for c in r["claims"][:3]]
            lines += [f"                 taken out: {c}" for c in r["taken_out"][:2]]
        lines.append("")
    lines += [f"--- {len(extra)} accepted value and relation claims that are on no hand list (not judged; the lists are not complete)"]
    lines += [f"   {c.line()}" for c in extra]
    (folder / "compare.txt").write_text("\n".join(lines) + "\n")
    return totals


def summary(results, name):
    by_name = {p["name"]: p for p in PAPERS}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    lines = [f"Run '{name}' of the claim step and the graph step, code at commit {commit}, {time.strftime('%Y-%m-%d %H:%M')}",
             "Found = share of the hand-listed entries. Claims on no list are not judged.", "",
             f"{'paper':20s} {'split':11s} {'pages':>5s} {'claims':>6s} {'values: claims':>15s} {'graph':>9s} {'relations: claims':>18s} {'graph':>9s}  notes"]

    def share(found, listed):
        return f"{found}/{listed} {100 * found / max(listed, 1):3.0f}%"
    for split in ("development", "test", "all"):
        chosen = [r for r in results if split == "all" or by_name[r["paper"]]["split"] == split]
        if split != "all":
            for r in chosen:
                notes = "; ".join(str(r[k]) for k in ("claim_step_error", "graph_step_error") if k in r)
                lines.append(f"{r['paper']:20s} {split:11s} {by_name[r['paper']]['pages']:5d} {r['claims_accepted']:6d} "
                             f"{share(r['values_among_claims'], r['values_listed']):>15s} {share(r['values_in_graph'], r['values_listed']):>9s} "
                             f"{share(r['relations_among_claims'], r['relations_listed']):>18s} {share(r['relations_in_graph'], r['relations_listed']):>9s}  {notes}")
        total = {k: sum(r[k] for r in chosen) for k in ("claims_accepted", "values_listed", "values_among_claims", "values_in_graph",
                                                         "relations_listed", "relations_among_claims", "relations_in_graph")}
        lines.append(f"{'TOTAL ' + split:20s} {'':11s} {'':5s} {total['claims_accepted']:6d} "
                     f"{share(total['values_among_claims'], total['values_listed']):>15s} {share(total['values_in_graph'], total['values_listed']):>9s} "
                     f"{share(total['relations_among_claims'], total['relations_listed']):>18s} {share(total['relations_in_graph'], total['relations_listed']):>9s}")
        lines.append("")
    (HOME / f"{name}_summary.txt").write_text("\n".join(lines) + "\n")
    (HOME / f"{name}_summary.json").write_text(json.dumps({"commit": commit, "results": results}, indent=1))
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    name = next((a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--papers", "--workers"))), "run1")
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else [p["name"] for p in PAPERS]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 4
    job = (lambda p: compare(p, name)) if "--compare-only" in args else (lambda p: run(p, name))

    def safe(paper):
        try:
            done = job(paper)
            print(f"done {paper}: {done['claims_accepted']} claims", flush=True)
            return done
        except Exception as error:
            print(f"FAILED {paper}: {type(error).__name__}: {str(error)[:300]}", flush=True)
            return None
    with ThreadPoolExecutor(workers) as pool:
        results = [r for r in pool.map(safe, papers) if r]
    if len(papers) == len(PAPERS):
        print(summary(results, name))
