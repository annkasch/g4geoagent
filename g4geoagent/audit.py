"""System audit: what each box did and cost in a run, and the same across runs. A program, no LLM.

    python -m g4geoagent.audit <run folder> [<run folder> ...]

Reads log.jsonl of each run. The table across runs shows where time goes, which
checks find something, and where errors are caught, per box of the architecture.
"""

import json
import sys
from pathlib import Path

from g4geoagent.architecture import BOXES


def audit_run(folder):
    """Per box of the architecture: how often it was entered, model calls, seconds in model calls,
    and what it found. Plus the outcome of the run."""
    events = [json.loads(line) for line in (Path(folder) / "log.jsonl").read_text().splitlines()]
    boxes = {name: {"entered": 0, "model_calls": 0, "model_seconds": 0.0, "found": 0}
             for name, box in BOXES.items() if box["kind"] != "data"}
    outcome = {"pieces": 0, "pieces_valid": 0, "searches": 0, "papers_saved": 0, "figures": 0, "claims": 0,
               "revisions": 0, "revisions_accepted": 0, "stopped": "", "graded": False, "evaluator": {}}
    for event in events:
        names = [n for n in event.get("box") or [] if n in boxes]
        kind = event["kind"]
        for name in names:
            if kind == "box":
                boxes[name]["entered"] += 1
            elif kind == "llm_call":
                boxes[name]["model_calls"] += 1 / len(names)
                boxes[name]["model_seconds"] += event.get("seconds", 0) / len(names)
        if kind == "build_attempt" and event.get("outcome") == "problem" and "build" in boxes:
            boxes["build"]["found"] += 1                        # a script error, a load error or an overlap
        elif kind == "check" and event["stage"] == "measure_vs_claims" and not event.get("final"):
            boxes["measure_vs_claims"]["found"] += event.get("not met", 0) + (event.get("relations") or {}).get("not met", 0)
        elif kind == "finding":
            boxes[event["stage"]]["found"] += 1                 # look or final_look
        elif kind == "check" and event["stage"] == "integrate":
            boxes["integrate"]["found"] += len(event.get("not_met", []))
        elif kind == "check" and event["stage"] == "run_geant4":
            boxes["run_geant4"]["found"] += len(event.get("overlaps", [])) + len(event.get("problems", []))
        elif kind == "check" and event["stage"] == "compare_quotes":
            boxes["compare"]["found"] += sum(event.get("failing", {}).values())
        elif kind == "agreed":
            boxes["compare"]["found"] += event.get("disputed", 0) + event.get("dropped", 0)
            outcome["claims"] += event.get("both", 0) + event.get("only_one_confirmed", 0)
        elif kind == "piece":
            outcome["pieces"] += 1
            outcome["pieces_valid"] += bool(event.get("valid"))
        elif kind == "research":
            outcome["searches"] += 1
            outcome["papers_saved"] += len(event.get("files", []))
            outcome["figures"] += event.get("figures", 0)
            boxes["research"]["found"] += len(event.get("files", []))
        elif kind == "revision":
            outcome["revisions"] += 1
            outcome["revisions_accepted"] += bool(event.get("accepted"))
        elif kind == "output":
            outcome["stopped"] = event.get("stopped", "")
        elif kind == "check" and event["stage"] == "evaluator":
            outcome["graded"] = bool(event.get("graded"))
            boxes["evaluator"]["found"] += event.get("findings", 0)
    grade = Path(folder) / "evaluation" / "grade.json"
    if grade.exists():
        for finding in json.loads(grade.read_text())["findings"]:
            outcome["evaluator"][finding["kind"]] = outcome["evaluator"].get(finding["kind"], 0) + 1
    for box in boxes.values():
        box["model_calls"], box["model_seconds"] = round(box["model_calls"], 1), round(box["model_seconds"])
    return {"run": str(folder), "boxes": boxes, "outcome": outcome}


def table(audits):
    """The audits of several runs as text: one row per box, summed over the runs."""
    lines = [f"{len(audits)} run(s): " + ", ".join(Path(a["run"]).name for a in audits), "",
             f"{'box':22s} {'kind':8s} {'state':6s} entered  model calls  model minutes  found"]
    for name, box in BOXES.items():
        if box["kind"] == "data":
            continue
        total = {key: sum(a["boxes"][name][key] for a in audits) for key in ("entered", "model_calls", "model_seconds", "found")}
        lines.append(f"{name:22s} {box['kind']:8s} {box['state']:6s} {total['entered']:7d}  {total['model_calls']:11.0f}  "
                     f"{total['model_seconds'] / 60:13.1f}  {total['found']:5d}")
    lines.append("\n'found' is what the box caught or brought: script errors and overlaps (build), claims and plan "
                 "statements not met (measure), differences from figures (look, final look), interfaces not met "
                 "(integrate), failing or disputed claims (compare), papers saved (research), differences from the "
                 "public code (evaluator).")
    for audit in audits:
        o = audit["outcome"]
        lines.append(f"\n{Path(audit['run']).name}: {o['claims']} claims, {o['searches']} searches, {o['papers_saved']} papers and "
                     f"{o['figures']} figures saved, {o['pieces_valid']} of {o['pieces']} pieces valid, "
                     f"{o['revisions_accepted']} of {o['revisions']} revisions accepted. Stopped: {o['stopped']}. "
                     f"Evaluator: {o['evaluator'] or 'not graded'}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table([audit_run(folder) for folder in sys.argv[1:]]))
