"""Score builder variants: build each task from its description, then measure against the reference.

    python experiments/builder_bench.py [--seeds N] [--models a,b] [--variants x,y] [--tasks t1,t2]

Variants (style + feedback, see agent/builder.py):
  gdml         raw GDML, error feedback only          (baseline A of the proposal)
  py           pyg4ometry script, error feedback only (baseline B)
  py_measure   pyg4ometry script, plus Geant4's measurements of the build (self-measurement)
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from g4geoagent.agent.builder import build
from g4geoagent.agent.runlog import RunLog
from g4geoagent.evaluator.measure import measure

ROOT = Path(__file__).parents[1]
OUT = ROOT / "runs" / "builder_bench"
VARIANTS = {"gdml": ("gdml", "errors"), "py": ("pyg4ometry", "errors"), "py_measure": ("pyg4ometry", "measure")}


def option(name, default):
    args = sys.argv[1:]
    return args[args.index(name) + 1].split(",") if name in args else default


def one(job):
    variant, task, model, seed = job
    folder = OUT / variant / task / model.replace("/", "_") / f"seed{seed}"
    result_file = folder / "result.json"
    if result_file.exists():
        return job, json.loads(result_file.read_text())
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "log.jsonl").unlink(missing_ok=True)
    style, feedback = VARIANTS[variant]
    specification = (ROOT / "tasks" / task / "docs" / "description.md").read_text()
    try:
        built = build(specification, model, folder, style, feedback, log=RunLog(folder / "log.jsonl"), seed=seed)
    except Exception as error:
        built = {"gdml": None, "valid": False, "attempts": 0, "finished": f"{type(error).__name__}: {str(error)[:120]}"}
    result = {"attempts": built["attempts"], "finished": built["finished"], "valid": built["valid"]}
    if built["gdml"]:
        meta = yaml.safe_load((ROOT / "tasks" / task / "meta.yaml").read_text())
        m = measure(built["gdml"], ROOT / "tasks" / task / "reference" / "reference.gdml", meta["evaluate"]["region_mm"])
        result.update({k: m[k] for k in ("agreement", "lines_matching", "extra", "mass", "differences")})
    result_file.write_text(json.dumps(result, indent=1))
    return job, result


if __name__ == "__main__":
    seeds = int(option("--seeds", ["2"])[0])
    models = option("--models", ["lbl/gpt-oss-120b", "lbl/gemma-4"])
    variants = option("--variants", list(VARIANTS))
    tasks = option("--tasks", ["bege", "icpc_p43511a"])
    jobs = [(v, t, m, s) for v in variants for t in tasks for m in models for s in range(seeds)]
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, jobs))
    print(f"{'variant':11s} {'task':13s} {'model':17s} valid builds  attempts  agreement  lines matching  mass difference")
    for variant in variants:
        for task in tasks:
            for model in models:
                rs = [r for (v, t, m, _), r in results if (v, t, m) == (variant, task, model)]
                good = [r for r in rs if r.get("agreement") is not None]
                mean = lambda key: sum(r[key] for r in good) / len(good) if good else float("nan")
                mass = [abs(r["mass"]["difference"]) for r in good if r.get("mass") and r["mass"]["difference"] is not None]
                print(f"{variant:11s} {task:13s} {model[4:]:17s} {len(good):5d}/{len(rs):<6d} "
                      f"{sum(r['attempts'] for r in rs) / len(rs):8.1f}  {mean('agreement'):8.1%}  {mean('lines_matching'):13.1%}  "
                      f"{(sum(mass) / len(mass) if mass else float('nan')):13.1%}")
