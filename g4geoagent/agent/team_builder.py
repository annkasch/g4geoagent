"""The builder of a team: from the team's brief and the figures it has, the geometry specification of its parts.

The model (lbl/gemma-4, which sees pictures) writes a specification (geometry_spec.TeamSpec); a program checks it and
sends what fails back, up to three times; the program writes the GDML; Geant4 loads it, checks overlaps and weighs
every volume; the masses are compared with the masses the plan held back for checking.
"""

import json
import re
from pathlib import Path

from g4geoagent.agent import detector_graph as D
from g4geoagent.agent import geometry_spec as GS
from g4geoagent.agent import graph as G
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.inspector.geant4_run import geant4_run
from g4geoagent.reviewer.look import _image

MODEL = "lbl/gemma-4"

PROMPT = """You are the builder of the team "{team}" for a Geant4 geometry model of the detector {detector}. You do \
not write code. You write a geometry specification of your team's parts, which a program turns into Geant4 volumes.

YOUR PARTS, from the build plan (each with its values and the sentences of the papers behind them):
{brief}

EVERY SENTENCE OF THE PAPERS THAT NAMES ONE OF YOUR PARTS (the plan above may have attached some of them wrongly; the \
sentences are the source of truth):
{sentences}

FIGURES you have: {figure_list}

How to build
- A part can be several volumes, and a volume's solid can be made of several solids: a vessel is a shell with a \
bottom and a flange, a shield is a cup, a plate has holes. Choose the shapes from what the sentences say, what the \
figures show, and what such a part is usually like.
- Solids: tube (rmin, rmax, length; optional sphi, dphi), cone (rmin1, rmax1, rmin2, rmax2, length), box (x, y, z), \
sphere (rmin, rmax; optional theta_start, theta_delta), torus (rmin, rmax, rtor), polycone (points: z, rmin, rmax from \
bottom to top; a closed bottom has rmin 0; a step is two points at the same z), polyhedra (sides; points as \
polycone), extrusion (corners in x-y; thickness), union / subtraction / intersection (first, second; position and \
rotation of the second relative to the first). Lengths are full lengths, not half lengths. Every solid is centred \
on its own origin except polycone and polyhedra, whose z values are their own.
- Build in the team's own frame: put your outermost volume at the origin and the others relative to it. Another \
team's parts are not yours to build; where yours sit relative to theirs is for the Coordinator.

Where every number comes from, in this order of preference
1 stated: written in the text of a paper; give the claim ids, and the number exactly as the claim has it.
2 written_in_figure: a number written in a figure, such as a dimension label; give the claim ids.
3 derived: worked out from other numbers by a rule; give the rule in why (inner radius = outer radius - wall).
4 researched: from a source found by research; give the claim ids. (No research has been done yet.)
5 measured_from_figure: do not use. Measuring a figure is done by a program, on request, only when nothing above exists.
6 estimated: your judgement; give the reasoning in why (what such a part usually is, what the figure suggests).
Use figures for shapes, for what is inside or above what, and to tell which of several readings of a stated value \
is meant (an inner or an outer radius). Do not read sizes off a figure.

When the sentences disagree with each other or with the plan (two thicknesses for one part, a part that seems to \
belong elsewhere), do not choose silently: build from the best supported reading, and write the conflict under \
questions for the Coordinator. A part of the brief you do not build goes under left_out, with the reason.
Under shapes, write for each part the shape you chose and what it rests on.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def sentences_for(brief, graph, claims):
    """Every accepted claim whose sentence names one of the team's parts, by its name or another name in the graph."""
    mine = {t["part"] for t in brief["tasks"]}
    names = set()
    for n in graph["nodes"]:
        if n["name"] in mine:
            for x in (n["name"], *n.get("also_called", [])):
                names.add(re.sub(r"[_\s]+", " ", x.lower()).strip())
    words = sorted({w for x in names for w in [x] if len(w) > 3}, key=len, reverse=True)
    out = []
    for c in claims.values():
        if c.status != "accepted":
            continue
        text = re.sub(r"[_\s]+", " ", f"{c.statement or c.line()} {' '.join(c.parts)}".lower())
        if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
            out.append(c)
    return out


def build_spec(brief, brief_as_text, graph, claims, figures, log=None, model=MODEL):
    """The specification of the team's parts. `figures`: [(path, caption)]. Returns (TeamSpec, rounds of problems)."""
    said = sentences_for(brief, graph, claims)
    request = PROMPT.format(team=brief["team"], detector=brief["detector"], brief=brief_as_text,
                            sentences="\n".join(f"  {c.id} (p. {c.page}): {c.statement or c.line()}" for c in said),
                            figure_list="; ".join(f"figure {i + 1}: {caption}" for i, (_, caption) in enumerate(figures)) or "none",
                            schema=json.dumps(GS.TeamSpec.model_json_schema(), separators=(",", ":")))
    content = [{"type": "text", "text": request}] + [_image(path) for path, _ in figures]
    return D._with_repairs(model, [{"role": "user", "content": content}], GS.TeamSpec,
                           lambda s: GS.check(s, brief, claims, GS.known_material), log, "team_builder")


def weigh(spec, folder, brief):
    """GDML, Geant4 run and the mass check of a specification. Returns a report dict."""
    folder = Path(folder)
    gdml = folder / "team.gdml"
    GS.to_gdml(spec, gdml)
    run = geant4_run(gdml)
    masses = {}
    for p in run.get("parts", []):
        name = (p.get("name") or p.get("volume") or p.get("logical") or "").removesuffix("_lv")
        masses[name] = masses.get(name, 0) + p.get("mass_g", 0) / 1e6
    by_part = {}
    for v in spec.volumes:
        by_part[v.part] = by_part.get(v.part, 0) + masses.get(v.name, 0)
    held = []
    for t in brief["tasks"]:
        for h in t["held_back"]:
            if h.get("quantity") == "mass":
                factor = {"t": 1, "ton": 1, "tons": 1, "tonne": 1, "tonnes": 1, "kg": 1e-3, "g": 1e-6}.get(str(h.get("unit", "")).lower(), None)
                if factor is not None and t["part"] in by_part:
                    stated = float(h["value"]) * factor
                    held.append({"part": t["part"], "stated_t": stated, "built_t": round(by_part[t["part"]], 3),
                                 "ratio": round(by_part[t["part"]] / stated, 2) if stated else None, "claims": h["claims"]})
    return {"gdml": str(gdml), "loaded": run.get("loaded"), "ok": run.get("ok"), "overlaps": run.get("overlaps"),
            "problems": run.get("problems", [])[:10], "masses_t": {k: round(v, 3) for k, v in masses.items()},
            "held_back_masses": held, "origins": GS.origins(spec)}
