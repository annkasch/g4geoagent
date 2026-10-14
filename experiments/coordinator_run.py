"""Run the coordinator on the finished graphs and geometry views of a run, and print what a program can tell.

    python experiments/coordinator_run.py <run name> <variant> [--papers a,b] [--workers 5] [--no-objections] [--seed N] [--model lbl/...]

For each paper reads runs/papers20/<paper>/<run>/ (detector_graph.json, geometry_view.json, claims.jsonl) and writes
the plan into runs/papers20/<paper>/<run>/coordinator/<variant>/: build_plan.json, build_plan.txt, the model calls in
log.jsonl, and, if the coordinator objected, the graph and view as the graph builder answered. Variants are kept
side by side. Without --papers: the five development papers that have a view. --seed N gives an independent
run (CBorg caches identical requests); it is written to <variant>_s<N>.
The score cannot tell whether the cuts and the envelopes are sensible: look at build_plan.txt.
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

import first_run as F                                  # noqa: E402
from g4geoagent.agent import coordinator as K          # noqa: E402
from g4geoagent.agent import llm as L                  # noqa: E402
from g4geoagent.agent.runlog import RunLog             # noqa: E402

MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else K.PLAN_MODEL
DEVELOPMENT = ["cuore_cryostat", "t2k_fgd", "xenonnt", "antares", "veritas"]


def one(paper, name, variant, objections):
    folder = F.HOME / paper / name
    out = folder / "coordinator" / variant
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        plan = K.coordinate(folder, F.detector_name(paper), RunLog(out / "log.jsonl"), model=MODEL, objections=objections, out=out)
    except Exception as error:
        return {"paper": paper, "error": f"{type(error).__name__}: {str(error)[:300]}"}
    answers = plan.get("graph_answers", {}).get("answers", [])
    return {"paper": paper, **plan["score"], "seconds": round(time.time() - started),
            "changed": sum(a["decision"] == "change" and bool(a["made"]) for a in answers),
            "kept_by_graph": sum(a["decision"] == "keep" for a in answers)}


if __name__ == "__main__":
    args = sys.argv[1:]
    name, variant = args[0], args[1]
    if "--seed" in args:
        L.DEFAULT_OPTIONS["seed"] = int(args[args.index("--seed") + 1])
        variant += f"_s{L.DEFAULT_OPTIONS['seed']}"
    papers = args[args.index("--papers") + 1].split(",") if "--papers" in args else DEVELOPMENT
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 5
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(lambda p: one(p, name, variant, "--no-objections" not in args), papers))
    (F.HOME / f"{name}_coordinator_{variant}.json").write_text(json.dumps(rows, indent=1))
    keys = ["kept", "teams", "unassigned", "interfaces", "unanswered", "values", "open", "derived", "problems_left",
            "exact", "lumped", "repeats", "gaps", "objections", "changed", "kept_by_graph", "seconds"]
    print(f"{'paper':16s} " + " ".join(f"{k[:7]:>7s}" for k in keys))
    for r in rows:
        print(f"{r['paper']:16s} " + (r["error"] if "error" in r else " ".join(f"{r[k]:7d}" for k in keys)))
