"""Read the nine figures with sketches and comparison rounds, snap the boxes to image edges, write the sketches.

    python experiments/layout_sketch_run.py <out folder> [--rounds 3]
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from g4geoagent.agent import figure_layout as FL     # noqa: E402
from g4geoagent.agent.runlog import RunLog          # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 3
figures = sorted(p for p in (ROOT / "runs/layout/figures").glob("*.png") if not p.stem.endswith("_view"))


def one(figure):
    try:
        layout, drawn = FL.read_with_sketches(figure, out, log=RunLog(out / "log.jsonl"), rounds=rounds)
    except Exception as error:
        return f"{figure.name}: {type(error).__name__}: {str(error)[:200]}"
    (out / f"{figure.stem}.json").write_text(layout.model_dump_json(indent=1))
    snapped = FL.snap(layout, FL._larger(figure))
    for p in layout.parts:
        if p.id in snapped:
            p.box = snapped[p.id][1]
    FL.sketch(layout, FL._larger(figure), out / f"{figure.stem}_snapped.png")
    (out / f"{figure.stem}.txt").write_text(FL.as_text(layout) + "\n" + "\n".join(
        f"  {p.profile and p.id + ' profile: ' + p.profile}" for p in layout.parts if p.profile) + "\n")
    return f"{figure.name}: {len(drawn)} sketches"


with ThreadPoolExecutor(5) as pool:
    for line in pool.map(one, figures):
        print(line, flush=True)
