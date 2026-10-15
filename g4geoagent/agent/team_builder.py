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
from pydantic import BaseModel, Field
from typing import Literal

MODEL = "lbl/gemma-4"
SHAPES_FIRST = True        # a call of its own decides the shape of each part from the figure, before any number
CONTEXT = False            # each sentence is shown with the sentences around it in the paper

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
- Building blocks, to use whenever they fit: cylinder (radius, height): a solid cylinder or disk; hollow_cylinder \
(outer_radius, wall, height): a tube or ring open at both ends; cup (outer_radius, wall, bottom, height; open: top or \
bottom): a hollow cylinder closed at one end.
- Other solids: tube (rmin, rmax, length; optional sphi, dphi), cone (rmin1, rmax1, rmin2, rmax2, length), box (x, y, z), \
sphere (rmin, rmax; optional theta_start, theta_delta), torus (rmin, rmax, rtor), polycone (points: z, rmin, rmax from \
bottom to top; a closed bottom has rmin 0; a step is two points at the same z), polyhedra (sides; points as \
polycone), extrusion (corners in x-y; thickness), union / subtraction / intersection (first, second; position and \
rotation of the second relative to the first). Lengths are full lengths, not half lengths. Every solid, building \
blocks and profiles alike, is centred on its own origin: a solid 178 cm high reaches from z = -89 to +89 cm. A \
volume's position is the position of that centre.
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

Reading the sentences
- A part described by a thickness and a radius, with no hollow or opening mentioned, is a disk or slab: its thickness \
is its height. A wall thickness belongs to a shell, a vessel or a cup, and the sentences or the figure say so.
- A mass is never a target. Do not choose or change a size to make a mass come out right. A stated size stays as \
stated; an estimated size changes only when a sentence or the figure supports the change. When a mass that the \
papers state disagrees with what you built, report it under questions.

When the sentences disagree with each other or with the plan (two thicknesses for one part, a part that seems to \
belong elsewhere), do not choose silently: build from the best supported reading, and write the conflict under \
questions for the Coordinator. A part of the brief you do not build goes under left_out, with the reason.
Under shapes, write for each part the shape you chose and what it rests on.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


class Relative(BaseModel):
    other: str = Field(description="another of your parts")
    where: Literal["inside_its_hollow_top", "inside_its_hollow_bottom", "inside_its_hollow_centre", "above", "below",
                   "around", "beside", "apart"] = Field(description="where THIS part is relative to the other")


class ShapeDecision(BaseModel):
    part: str
    in_figure: str = Field(description="where the figure shows this part (panel, label, colour), or 'not shown'")
    hollow: bool = Field(description="true if the figure or the sentences show a cavity inside the part")
    block: Literal["cylinder", "hollow_cylinder", "cup", "other"] = Field(description="the building block that fits; 'other' only if none does")
    opening: Literal["none", "top", "bottom", "both"] = "none"
    build: bool = Field(description="false if the part seems to belong to another team or outside this subsystem")
    relative: list[Relative] = Field(default_factory=list, description="where this part is relative to each of your other parts")
    inside_of: str = Field(default="", description="filled by the program from relative")
    where_inside: Literal["top", "bottom", "centre", ""] = Field(default="", description="filled by the program from relative")
    why: str = Field(description="what the decision rests on: what the figure shows, which sentences")


class ShapeDecisions(BaseModel):
    decisions: list[ShapeDecision]


SHAPE_PROMPT = """You are the builder of the team "{team}" for a Geant4 geometry model of the detector {detector}. Before \
any number, decide the shape of each of your parts. Look at the figure carefully, part by part.

YOUR PARTS:
{brief}

EVERY SENTENCE THAT NAMES ONE OF YOUR PARTS:
{sentences}

FIGURES: {figure_list}

For every part of the brief answer:
- in_figure: where the figure shows it (panel, label, colour), or "not shown".
- hollow: does the figure show a cavity inside it, or do the sentences mention one? A block drawn filled with one \
colour is solid.
- block: cylinder (a solid cylinder, disk or slab), hollow_cylinder (a tube or ring open at both ends), cup (a hollow \
cylinder closed at one end), or other.
- opening: for a cup, the open end.
- build: false if the sentences or the figure suggest the part is not inside your subsystem (for example, it covers a \
part that another team builds, or it is outside the cryostat); such a part goes to the Coordinator as a question.
- relative: for EVERY other part of yours, where this part is relative to it, as the figure shows: inside its hollow \
(at the top, bottom or centre of the hollow), above, below, around, beside, or apart. A part drawn between the walls \
of a cup is inside its hollow. A program places a part that is inside another's hollow.
- why: what you see in the figure and which sentences you rely on.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def shape_check(answer, brief):
    parts = {t["part"] for t in brief["tasks"]}
    given = {d.part for d in answer.decisions}
    problems = []
    for d in answer.decisions:
        named = {r.other for r in d.relative}
        missing = sorted(parts - {d.part} - named)
        if missing:
            problems.append(f"part {d.part}: say where it is relative to {', '.join(missing)}")
        problems += [f"part {d.part}: '{r.other}' is not another part of the brief" for r in d.relative if r.other not in parts or r.other == d.part]
        inside = [r for r in d.relative if r.where.startswith("inside_its_hollow")]
        if len(inside) > 1:
            problems.append(f"part {d.part}: it can be inside the hollow of one part only, not of {', '.join(r.other for r in inside)}")
    if problems:
        return problems
    problems = [f"no decision for part {p}" for p in sorted(parts - given)]
    problems += [f"'{p}' is not a part of the brief" for p in sorted(given - parts)]
    problems += [f"part {d.part}: a cup needs its open end (top or bottom)" for d in answer.decisions if d.block == "cup" and d.opening not in ("top", "bottom")]
    return problems


def decide_shapes(brief, brief_as_text, said, figures, log=None, model=MODEL, documents=None):
    request = SHAPE_PROMPT.format(team=brief["team"], detector=brief["detector"], brief=brief_as_text,
                                  sentences=listing(said, documents),
                                  figure_list="; ".join(f"figure {i + 1}: {caption}" for i, (_, caption) in enumerate(figures)) or "none",
                                  schema=json.dumps(ShapeDecisions.model_json_schema(), separators=(",", ":")))
    content = [{"type": "text", "text": request}] + [_image(_larger(path)) for path, _ in figures]
    answer, rounds = D._with_repairs(model, [{"role": "user", "content": content}], ShapeDecisions, lambda a: shape_check(a, brief), log, "team_shapes")
    for d in answer.decisions:
        inside = next((r for r in d.relative if r.where.startswith("inside_its_hollow")), None)
        if inside:
            d.inside_of, d.where_inside = inside.other, inside.where.rsplit("_", 1)[1]
    return answer, rounds


def _larger(path, factor=2):
    """The figure at twice its size, for the shape step (small drawings lose their thin walls)."""
    from PIL import Image
    path = Path(path)
    out = path.with_name(path.stem + f"_x{factor}.png")
    if not out.exists():
        im = Image.open(path)
        im.resize((im.width * factor, im.height * factor), Image.LANCZOS).save(out)
    return out


def place(spec, decisions):
    """Put each part that was decided to sit in another part's hollow at its place there (top, bottom, centre), from
    the sizes of both. Returns notes for the builder: what was placed, and what does not fit."""
    notes = []
    volume_of = {v.part: v for v in spec.volumes}
    for d in decisions:
        if not (d.build and d.inside_of and d.part in volume_of and d.inside_of in volume_of):
            continue
        inner, outer = volume_of[d.part], volume_of[d.inside_of]
        so = next((x for x in spec.solids if x.name == outer.solid), None)
        prof_in, prof_out = GS.profile(spec, inner.solid), GS.profile(spec, outer.solid)
        if not (so and prof_in and prof_out and so.kind in ("cup", "hollow_cylinder")):
            notes.append(f"{d.part} could not be placed in {d.inside_of}: only a cup or hollow cylinder has a hollow the program can use")
            continue
        p = {k: GS._in_mm(v) for k, v in so.params.items()}
        low, high = -p["height"] / 2, p["height"] / 2
        if so.kind == "cup":
            low, high = (low + p["bottom"], high) if so.open == "top" else (low, high - p["bottom"])
        half = (prof_in[-1][0] - prof_in[0][0]) / 2
        oz = GS._in_mm(outer.position[2]) if len(outer.position) == 3 else 0.0
        z = {"top": high - half, "bottom": low + half, "centre": (low + high) / 2, "": (low + high) / 2}[d.where_inside] + oz
        rule = f"placed by the program at the {d.where_inside or 'centre'} of the hollow of {d.inside_of}"
        mk = lambda v, why: GS.Num(value=round(v / 10, 3), unit="cm", origin="derived", why=why)
        ox = outer.position[0] if len(outer.position) == 3 else mk(0, "on the axis")
        oy = outer.position[1] if len(outer.position) == 3 else mk(0, "on the axis")
        inner.position = [GS.Num(**ox.model_dump()), GS.Num(**oy.model_dump()), mk(z, rule)]
        inner.inside = outer.inside
        room = p["outer_radius"] - p["wall"]
        widest = max(b for _, _, b in prof_in)
        fits = widest <= room + 1e-6 and 2 * half <= high - low + 1e-6
        notes.append(f"{d.part} placed at the {d.where_inside or 'centre'} of the hollow of {d.inside_of}: z = {z / 10:g} cm"
                     + ("" if fits else f"; it does not fit: radius {widest / 10:g} cm in a hollow of radius {room / 10:g} cm, "
                                        f"height {2 * half / 10:g} cm in a hollow {(high - low) / 10:g} cm high"))
    return notes


def follows_shapes(spec, decisions):
    """Problems where the specification does not build a part with the block that was decided."""
    problems = []
    kinds = {}
    for v in spec.volumes:
        kinds.setdefault(v.part, set()).add(next((x.kind for x in spec.solids if x.name == v.solid), ""))
    for d in decisions:
        if not d.build and d.part in kinds:
            problems.append(f"part {d.part} was decided not to be built (it seems to belong elsewhere); leave it out and ask the Coordinator")
        elif d.build and d.block != "other" and d.part in kinds and d.block not in kinds[d.part]:
            problems.append(f"part {d.part} was decided to be a {d.block}, but is built as {', '.join(sorted(kinds[d.part]))}")
        elif d.build and d.block == "cup" and d.part in kinds:
            for v in spec.volumes:
                s = next((x for x in spec.solids if x.name == v.solid), None)
                if v.part == d.part and s and s.kind == "cup" and s.open != d.opening:
                    problems.append(f"part {d.part}: the cup was decided to be open at the {d.opening}, but is open at the {s.open}")
    return problems


def listing(said, documents=None):
    """The sentences naming the team's parts, one per line; with CONTEXT, each with the paper's sentences around it."""
    from g4geoagent.agent.compare import locate, sentences
    lines = []
    for c in said:
        line = f"  {c.id} (p. {c.page}): {c.statement or c.line()}"
        if CONTEXT and documents and c.quote:
            for text in documents.values():
                parts = sentences(text)
                found = sorted(locate(c.quote, text))
                if found:
                    around = " ".join(" ".join(parts[i].split()) for i in range(max(0, found[0] - 1), min(len(parts), found[-1] + 2)))
                    line += f"\n      in the paper: \"{around[:600]}\""
                    break
        lines.append(line)
    return "\n".join(lines)


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


def build_spec(brief, brief_as_text, graph, claims, figures, log=None, model=MODEL, documents=None):
    """The specification of the team's parts. `figures`: [(path, caption)]. Returns (TeamSpec, rounds of problems)."""
    said = sentences_for(brief, graph, claims)
    request = PROMPT.format(team=brief["team"], detector=brief["detector"], brief=brief_as_text,
                            sentences=listing(said, documents),
                            figure_list="; ".join(f"figure {i + 1}: {caption}" for i, (_, caption) in enumerate(figures)) or "none",
                            schema=json.dumps(GS.TeamSpec.model_json_schema(), separators=(",", ":")))
    content = [{"type": "text", "text": request}] + [_image(path) for path, _ in figures]
    return D._with_repairs(model, [{"role": "user", "content": content}], GS.TeamSpec,
                           lambda s: GS.check(s, brief, claims, GS.known_material), log, "team_builder")


def weigh(spec, folder, brief):
    """GDML, Geant4 run and the mass check of a specification. Returns a report dict."""
    folder = Path(folder)
    gdml = folder / "team.gdml"
    try:
        GS.to_gdml(spec, gdml)
    except Exception as error:
        return {"gdml": None, "loaded": False, "ok": False, "overlaps": [], "masses_t": {}, "held_back_masses": [],
                "problems": [f"the program could not write the geometry: {type(error).__name__}: {str(error)[:300]}"],
                "origins": GS.origins(spec)}
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


# ------------------------------------------------------------------ revisions: what was built goes back to the builder

def warnings(spec):
    """Things in a specification that are valid but probably not meant."""
    out = []
    for s in spec.solids:
        prof = GS.profile(spec, s.name)
        if not prof:
            continue
        for (z0, a0, b0), (z1, a1, b1) in zip(prof, prof[1:]):
            if z1 - z0 > 1 and abs(a1 - a0) > 1:
                out.append(f"solid {s.name}: the inner radius slopes from {a0 / 10:g} cm to {a1 / 10:g} cm over {(z1 - z0) / 10:g} cm "
                           f"(between z = {z0 / 10:g} and {z1 / 10:g} cm), so the hollow inside is a cone. If the inside should "
                           f"change in a step, give two points at the same z.")
            if z1 - z0 > 1 and abs(b1 - b0) > 1:
                out.append(f"solid {s.name}: the outer radius slopes from {b0 / 10:g} cm to {b1 / 10:g} cm over {(z1 - z0) / 10:g} cm. "
                           f"Is a cone meant? A step needs two points at the same z.")
    return out


def section_picture(spec, figures, path):
    """The built volumes cut through their axis, next to the first figure, as one PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Rectangle
    from PIL import Image
    colours = ["#22c7d6", "#e8a33d", "#4a90e2", "#9467bd", "#2ca02c", "#d62728", "#8c564b"]
    material_colour = {}
    fig, axes = plt.subplots(1, 2 if figures else 1, figsize=(13, 6.2) if figures else (6.5, 6.2))
    a = axes[0] if figures else axes
    top, side = 1.0, 1.0
    for v in spec.volumes:
        colour = material_colour.setdefault(v.material.lower(), colours[len(material_colour) % len(colours)])
        x0 = GS._in_mm(v.position[0]) / 10 if len(v.position) == 3 else 0
        z0 = GS._in_mm(v.position[2]) / 10 if len(v.position) == 3 else 0
        s = next(x for x in spec.solids if x.name == v.solid)
        prof = GS.profile(spec, v.solid)
        if prof:
            pts = [(z / 10 + z0, r0 / 10, r1 / 10) for z, r0, r1 in prof]
            for sign in (1, -1):
                a.add_patch(Polygon([(x0 + sign * r1, z) for z, r0, r1 in pts] + [(x0 + sign * r0, z) for z, r0, r1 in reversed(pts)],
                                    closed=True, fc=colour, ec="k", lw=0.6))
            top = max(top, max(abs(z) for z, _, _ in pts)); side = max(side, max(abs(x0) + r1 for _, _, r1 in pts))
        elif s.kind == "box":
            w, h = GS._in_mm(s.params["x"]) / 10, GS._in_mm(s.params["z"]) / 10
            a.add_patch(Rectangle((x0 - w / 2, z0 - h / 2), w, h, fc=colour, ec="k", lw=0.6))
            top = max(top, abs(z0) + h / 2); side = max(side, abs(x0) + w / 2)
        else:
            a.text(x0, z0, f"{v.name}\n({s.kind}, not drawn)", ha="center", fontsize=8)
    a.set_xlim(-side * 1.1, side * 1.1); a.set_ylim(-top * 1.08, top * 1.08); a.set_aspect("equal")
    a.set_xlabel("x (cm)"); a.set_ylabel("z (cm)")
    a.set_title("What you built, cut through the axis. Colours: " + ", ".join(f"{m}" for m in material_colour), fontsize=9)
    if figures:
        axes[1].imshow(Image.open(figures[0][0])); axes[1].axis("off"); axes[1].set_title("The figure", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def feedback(report, spec, brief):
    """What was found in a built attempt, as text for the builder."""
    lines = ["A program built your specification and Geant4 checked it."]
    if not report["loaded"]:
        lines.append("Geant4 could not load it: " + "; ".join(report["problems"][:5]))
    if report["overlaps"]:
        lines.append("These volumes overlap another volume: " + ", ".join(report["overlaps"]))
    for h in report["held_back_masses"]:
        lines.append(f"Part {h['part']}: built {h['built_t']} t; the papers state {h['stated_t']} t ({', '.join(h['claims'])}).")
    built = {v.part for v in spec.volumes}
    for t in brief["tasks"]:
        if t["part"] in built and not any(h["part"] == t["part"] for h in report["held_back_masses"]):
            lines.append(f"Part {t['part']}: built {sum(report['masses_t'].get(v.name, 0) for v in spec.volumes if v.part == t['part']):.3f} t; no stated mass.")
    lines.append("Where each round volume ends up in your team's frame:")
    for name, (zlo, zhi, r) in GS.extents(spec).items():
        lines.append(f"  {name}: from z = {zlo / 10:g} cm to z = {zhi / 10:g} cm, outer radius {r / 10:g} cm")
    lines += [f"Warning: {w}" for w in warnings(spec)]
    lines.append("The picture shows what you built cut through its axis, next to the figure. Compare shapes, proportions "
                 "and positions with the figure and with the sentences. A stated mass that disagrees with what you built is "
                 "not a target to fit: check the shapes and the readings of the sentences, and report what still disagrees "
                 "under questions.")
    lines.append("Send the complete revised specification as one JSON object. If nothing needs to change, send the same "
                 "specification again.")
    return "\n".join(lines)


def build_with_revisions(brief, brief_as_text, graph, claims, figures, folder, log=None, revisions=10, model=MODEL, documents=None):
    """Build, weigh, show; the builder revises from what was found, up to `revisions` times, and stops early when
    it sends the same specification again. Each attempt is kept in folder/attempt_<n>/. Returns the last attempt."""
    folder = Path(folder)
    said = sentences_for(brief, graph, claims)
    request = PROMPT.format(team=brief["team"], detector=brief["detector"], brief=brief_as_text,
                            sentences=listing(said, documents),
                            figure_list="; ".join(f"figure {i + 1}: {caption}" for i, (_, caption) in enumerate(figures)) or "none",
                            schema=json.dumps(GS.TeamSpec.model_json_schema(), separators=(",", ":")))
    attempts = []
    decisions = []
    if SHAPES_FIRST:
        answer, shape_rounds = decide_shapes(brief, brief_as_text, said, figures, log, model, documents)
        decisions = answer.decisions
        (folder / "shapes.json").write_text(json.dumps([d.model_dump() for d in decisions], indent=1))
        request += ("\n\nTHE SHAPES ARE DECIDED (build each part with this block; a part marked 'do not build' goes under "
                    "left_out with a question for the Coordinator):\n" + "\n".join(
                        f"  {d.part}: {'do not build' if not d.build else d.block + (' open at the ' + d.opening if d.block == 'cup' else '')}"
                        f"{' inside the hollow of ' + d.inside_of + ', at its ' + (d.where_inside or 'centre') if d.inside_of else ''}"
                        f" - {d.why}" for d in decisions)
                    + "\nA part that sits inside the hollow of another of your parts is placed there by the program; its "
                      "position in your specification is replaced.")
    messages = [{"role": "user", "content": [{"type": "text", "text": request}] + [_image(path) for path, _ in figures]}]
    check = lambda s: GS.check(s, brief, claims, GS.known_material) + follows_shapes(s, decisions)
    for number in range(revisions + 1):
        try:
            spec, rounds = D._with_repairs(model, messages, GS.TeamSpec, check, log, "team_builder" if number == 0 else "team_builder_revise")
        except Exception as error:
            attempts.append({"attempt": number, "error": str(error)[:300]})
            break
        placed = place(spec, decisions) if SHAPES_FIRST else []
        here = folder / f"attempt_{number}"
        here.mkdir(parents=True, exist_ok=True)
        (here / "spec.json").write_text(spec.model_dump_json(indent=1))
        (here / "spec.txt").write_text(GS.as_text(spec) + "\n")
        report = {"rounds": rounds, **weigh(spec, here, brief)}
        (here / "build.json").write_text(json.dumps(report, indent=1))
        section_picture(spec, figures, here / "section.png")
        same = bool(attempts) and attempts[-1].get("spec") == spec.model_dump()
        attempts.append({"attempt": number, "spec": spec.model_dump(), "folder": str(here)})
        if same or number == revisions:
            break
        for m in messages[1:]:          # the model takes at most four pictures: only the figures and the newest picture stay
            if m["role"] == "user" and isinstance(m["content"], list):
                m["content"] = [c for c in m["content"] if c.get("type") == "text"] + [{"type": "text", "text": "(the picture of this attempt is no longer shown)"}]
        messages.append({"role": "assistant", "content": spec.model_dump_json()})
        text = feedback(report, spec, brief) + ("\nPlaced by the program:\n" + "\n".join(f"  {n}" for n in placed) if placed else "")
        messages.append({"role": "user", "content": [{"type": "text", "text": text}, _image(here / "section.png")]})
    return attempts
