"""One team, one subsystem, end to end, one step at a time.

    python experiments/team_walk.py <step> [--run runs/wired/cuore_cryostat] [--team Shielding] [--out runs/team/cuore_shielding]

Steps, each reading what the step before wrote into the output folder:
    input     what the team receives from the build plan: its parts, their values with the claims behind them, the
              gaps, the interface it builds into, its relations to other teams. Writes team_input.json and .txt.
    build     the builder writes the geometry specification from the brief, the sentences naming its parts and the
              figures in the output folder (figure_*.png, caption in figure_*.txt); a program checks it, writes the
              GDML; Geant4 loads, checks overlaps and weighs it. Writes spec.json, spec.txt, team.gdml, build.json,
              pictures/.

Each step is written as the function the run will call for its box later (Teams, Build, Measure, Look).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from g4geoagent.agent import claims as C          # noqa: E402


def option(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


RUN = ROOT / option("--run", "runs/wired/cuore_cryostat")
TEAM = option("--team", "Shielding")
OUT = ROOT / option("--out", "runs/team/cuore_shielding")


def team_input(run, team):
    """What a team receives: its tasks from the build plan, each value and relation with the statements of its
    claims, the interface it builds into, and the relations that join its parts to other teams' parts."""
    plan = json.loads((run / "build_plan.json").read_text())
    claims = {c.id: c for c in C.load(run / "graph")}
    tasks = [t for t in plan["tasks"] if t["team"] == team]
    mine = {t["part"] for t in tasks}

    def said(ids):
        return [{"id": i, "statement": claims[i].statement or claims[i].line(), "quote": claims[i].quote,
                 "page": claims[i].page} for i in ids if i in claims]
    for t in tasks:
        for check in t["checks"]:
            check["said"] = said(check["claims"])
        t["said"] = said(t["claims"])
    return {"detector": plan["detector"], "team": team,
            "why": next((x["why"] for x in plan["teams"] if x["name"] == team), ""),
            "tasks": tasks,
            "interfaces": [i for i in plan["interfaces"] if i["inner_team"] == team or i["outer_team"] == team],
            "between_teams": [r for r in plan["between_teams"] if r["subject"] in mine or r["object"] in mine]}


def input_text(brief):
    lines = [f"Team {brief['team']} of {brief['detector']}: {brief['why']}", ""]
    for t in brief["tasks"]:
        repeat = f", {t['repeat']} times" if t.get("repeat") else ""
        lines.append(f"PART {t['part']} ({t['what']})")
        lines.append(f"  inside {t['inside']}; shape {t['shape']}, {t['form']}{repeat}; level proposed by the Coordinator: {t['level']}")
        for check in t["checks"]:
            if "quantity" in check:
                head = f"{check['quantity']} = {check['value']} {check['unit']}".strip()
            else:
                head = f"{check['subject']} {check['relation']} {check['object']}"
            lines.append(f"  - {head}")
            for s in check["said"]:
                lines.append(f"      {s['id']} (p. {s['page']}): {s['statement'][:150]}")
        if t["held_back"]:
            lines.append(f"  held back for checking, not given to the builder: {', '.join(str(h) for h in t['held_back'])}")
        if t["gaps"]:
            lines.append(f"  gaps: {', '.join(g['what'] + ' (' + g['effort'] + ')' for g in t['gaps'])}")
        lines.append("")
    for i in brief["interfaces"]:
        values = "; ".join(f"{v['quantity']}: {'OPEN' if v.get('open') else v['value']} {v.get('unit', '')}".strip() for v in i["values"])
        lines.append(f"INTERFACE {i['id']}: {i['inner_team']} builds {', '.join(i['inner'])} into {i['outer']} "
                     f"(team {i['outer_team']}); envelope {i['shape']}; {values}")
    for r in brief["between_teams"]:
        lines.append(f"RELATION TO ANOTHER TEAM: {r['subject']} {r['relation']} {r['object']} ({', '.join(r['claims'])})")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    step = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    if step == "input":
        brief = team_input(RUN, TEAM)
        (OUT / "team_input.json").write_text(json.dumps(brief, indent=1))
        (OUT / "team_input.txt").write_text(input_text(brief))
        print(input_text(brief))
    elif step == "build":
        from g4geoagent.agent import geometry_spec as GS
        from g4geoagent.agent import team_builder as TB
        from g4geoagent.agent.runlog import RunLog
        from g4geoagent.inspector.render3d import render
        brief = json.loads((OUT / "team_input.json").read_text())
        graph = json.loads((RUN / "graph" / "detector_graph.json").read_text())
        claims = {c.id: c for c in C.load(RUN / "graph")}
        figures = [(f, (f.with_suffix(".txt").read_text().strip() if f.with_suffix(".txt").exists() else f.stem))
                   for f in sorted(OUT.glob("figure_*.png"))]
        spec, rounds = TB.build_spec(brief, input_text(brief), graph, claims, figures, RunLog(OUT / "log.jsonl"))
        (OUT / "spec.json").write_text(spec.model_dump_json(indent=1))
        (OUT / "spec.txt").write_text(GS.as_text(spec) + "\n")
        report = {"rounds": rounds, **TB.weigh(spec, OUT, brief)}
        (OUT / "build.json").write_text(json.dumps(report, indent=1))
        if report["loaded"]:
            render(OUT / "team.gdml", OUT / "pictures", f"{brief['detector']}: team {brief['team']}")
        print(GS.as_text(spec)); print(json.dumps({k: v for k, v in report.items() if k != "rounds"}, indent=1))
        print("problems per repair round:", [len(r) for r in rounds], "\nlast:", rounds[-1][:8])
    else:
        raise SystemExit(f"unknown step {step!r}")
