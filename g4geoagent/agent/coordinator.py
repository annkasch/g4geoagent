"""Coordinator: plans the build of the whole detector before anything is built.

    python -m g4geoagent.agent.coordinator <folder with detector_graph.json and geometry_view.json> [--name "CUORE"]

The build plan (`build_plan`) works from the detector graph and its geometry view and does not change the layout.
A model cuts the kept tree into teams, sets detail levels where the graph's marks are wrong, confirms repeated parts and
objects to entries of the graph; a second call writes the interfaces where one team builds into another team's part.
A program checks both answers and turns them into tasks, one per piece. Objections go back to the graph builder
(detector_graph.answer_objections), and the plan is made once more on the graph it returns.

The layout plan (`make_plan`) is the earlier coordinator, which worked out the layout itself from the claims.
pipeline.py still uses it until the run is wired to the graph.
"""

import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from g4geoagent.agent import claims as C
from g4geoagent.agent import detector_graph as D
from g4geoagent.agent.compare import numbers_in
from g4geoagent.agent.llm import call_llm_json

MODEL = "lbl/gpt-oss-120b"     # the layout plan
# the build plan: gemma-4 cut the teams the same way in two independent runs on all five development papers, where
# gpt-oss-120b swung between one and eleven teams (experiments/notes/coordinator.md, rounds 8 and 9)
PLAN_MODEL = "lbl/gemma-4"
RELATIONS = ("inside", "surrounds", "centred_in", "at_bottom_of", "at_top_of", "outside")


class PartPlan(BaseModel):
    name: str
    inside: str = Field(description="Name of the part that directly contains it, or 'world'")
    form: Literal["solid", "hollow", "filling"] = Field(
        description="'hollow' for a vessel, tube, shell or wall that has other parts or a filling inside; "
                    "'filling' for the liquid or gas inside a vessel; 'solid' otherwise")
    detail: Literal["exact", "simplified", "lumped"] = Field(
        description="'exact' for sensitive parts and what is close to them; 'simplified' for large structures "
                    "further away; 'lumped' for small parts such as cables, screws and electronics")
    team: str = Field(description="Short name of the subsystem this part belongs to, e.g. 'water_tank', 'cryostat', 'array'")


class Relation(BaseModel):
    part: str
    relation: Literal["inside", "surrounds", "centred_in", "at_bottom_of", "at_top_of", "outside"]
    other: str


class Plan(BaseModel):
    parts: list[PartPlan]
    relations: list[Relation] = Field(description="How parts are arranged, each backed by a claim or by the documents' description")


def make_plan(detector, parts, claims_text, figure_notes="", log=None, model=MODEL):
    """The layout plan for `parts` ({name: Part}). Parts the model leaves out keep what the readers said."""
    request = (f"You plan the geometry model of the detector {detector} for a particle simulation. Other agents will "
               "build it from your plan, so the plan must settle the layout.\n\n" + claims_text
               + ("\n\nWhat the figures of the documents show:\n" + figure_notes if figure_notes else "") +
               "\n\nWrite the plan:\n"
               "- For every part: what directly contains it, its form, its detail level and its team. Work from the "
               "outside in. A vessel is 'hollow', what fills it is a 'filling' inside the vessel, and what sits in the "
               "liquid is inside the filling. A part that surrounds or encloses other parts is 'hollow', never 'solid'. "
               "If the documents name a vessel but not its filling, add the filling as a part. Merge parts that are the "
               "same thing under two names, and keep the name used in the claims.\n"
               "- Relations: every statement of the documents about where a part is, as one of: "
               "inside, surrounds, centred_in, at_bottom_of, at_top_of, outside. Use only part names of your plan.\n"
               "- Teams: 2 to 5 subsystems that can be built one after the other from the outside in.\n\n"
               "Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Plan.model_json_schema(), separators=(",", ":")))
    try:
        plan, _ = call_llm_json(model, [{"role": "user", "content": request}], Plan, log=log,
                                stage="coordinator_plan", temperature=0)
    except ValueError:
        plan = Plan(parts=[], relations=[])
    known = {p.name for p in plan.parts}
    for name, part in parts.items():            # nothing the readers found is dropped silently
        if name not in known:
            plan.parts.append(PartPlan(name=name, inside=part.inside if part.inside in parts else "world",
                                       form="solid", detail="simplified", team="other"))
    names = {p.name for p in plan.parts}
    for part in plan.parts:
        if part.inside not in names or part.inside == part.name:
            part.inside = "world"
    plan.relations = [r for r in plan.relations if r.part in names and r.other in names and r.part != r.other]
    return plan


def outside_in(plan):
    """Part names ordered from the outermost to the innermost."""
    inside = {p.name: p.inside for p in plan.parts}

    def depth(name, seen=()):
        mother = inside.get(name, "world")
        return 0 if mother == "world" or mother in seen else 1 + depth(mother, (*seen, name))
    return sorted(inside, key=depth)


def teams(plan):
    """[(team name, [parts])], teams ordered by their outermost part, parts from the outside in."""
    order, found = outside_in(plan), {}
    team_of = {p.name: p.team for p in plan.parts}
    for name in order:
        found.setdefault(team_of[name], []).append(name)
    return list(found.items())


def plan_text(plan, parts=None):
    """The plan as text for a builder, all of it or only for `parts`."""
    lines = ["Layout plan (part: inside what; form; detail level):"]
    lines += [f"  {p.name}: inside {p.inside}; {p.form}; {p.detail}" for p in plan.parts if parts is None or p.name in parts]
    relations = [r for r in plan.relations if parts is None or (r.part in parts and r.other in parts)]
    if relations:
        lines.append("Arrangement that the build must show:")
        lines += [f"  {r.part} {r.relation.replace('_', ' ')} {r.other}" for r in relations]
    return "\n".join(lines)


# ------------------------------------------------------------------ the build plan, from the detector graph

LEVEL = {"sensitive": "exact", "main_structure": "simplified", "small_part": "lumped"}
EFFORT = {"exact": "targeted search: documents, datasheets, figures, then online",
          "simplified": "one search, then an estimate", "lumped": "a mass estimate"}
HELD_BACK = {"mass"}        # stated masses of built parts go to the Inspector, not to the builder (proposal 5.3, point 4)
NESTING = {"contains", "encloses", "consists_of"}
LENGTHS = ("km", "m", "cm", "mm", "um", "μm", "µm", "in", "ft")


class Team(BaseModel):
    name: str = Field(description="Short name of the subsystem, e.g. 'shield', 'cryostat', 'array'")
    roots: list[str] = Field(description="The parts it builds with everything inside them, except what is inside "
                                         "the root of another team")
    why: str = ""


class Level(BaseModel):
    part: str
    level: Literal["exact", "simplified", "lumped"]
    why: str


class Repeat(BaseModel):
    part: str
    count: int
    claims: list[str] = Field(description="Ids of the claims that give the count")


class Objection(BaseModel):
    entry: str = Field(description="The entry of the graph, e.g. 'helium_gas: material = polytetrafluoroethylene' "
                                   "or 'dilution_refrigerator inside cryostat'")
    problem: str = Field(description="What is wrong with it, with the id of the claim that shows it")


class Levels(BaseModel):
    levels: list[Level] = Field(description="One entry for every part of the tree")


class Split(BaseModel):
    teams: list[Team]
    repeats: list[Repeat] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)


class Value(BaseModel):
    quantity: str = Field(description="e.g. 'inner diameter', 'inner height', 'height of the floor above the bottom'")
    value: float | str | None = None
    unit: str = ""
    claims: list[str] = Field(default_factory=list)
    derived: bool = Field(default=False, description="true if worked out from the claims and not stated by one")
    reasoning: str = Field(default="", description="For a derived value: how it follows")
    open: bool = Field(default=False, description="true if the documents do not give it; then value is null")
    note: str = Field(default="", description="For an open value: what is missing")


class Interface(BaseModel):
    id: str
    shape: Literal["cylinder", "tube", "box", "sphere", "plate", "other", "not_stated"]
    values: list[Value]
    placement: str = Field(default="", description="Where the inner parts sit in the envelope, as the documents say "
                                                     "(centred, on the bottom, hanging from the lid); '' if they do not say")


class Interfaces(BaseModel):
    interfaces: list[Interface]


def kept_tree(data, view):
    """(nodes {name: node} of the kept parts in outside-in order, contents {kept part: [collapsed parts]})."""
    keep = set(view["keep"])
    everything = {n["name"]: n for n in data["nodes"]}
    children = {}
    for n in data["nodes"]:
        children.setdefault(n["inside"], []).append(n["name"])
    order = []

    def walk(parent):
        for name in sorted(children.get(parent, [])):
            if name in keep:
                order.append(name)
                walk(name)
    walk("world")
    contents = {}
    for name in view["collapse"]:
        up = everything[name]["inside"]
        while up in everything and up not in keep:
            up = everything[up]["inside"]
        if up in keep:
            contents.setdefault(up, []).append(name)
    return {name: everything[name] for name in order}, contents


def _value_text(p):
    which = "" if p["which"] in ("", "not_stated") else f" ({p['which']})"
    return f"{p['quantity']}{which} {p['value']} {p['unit']}".strip() + f" [{', '.join(p['claims'])}]"


def _tree_text(data, view):
    nodes, contents = kept_tree(data, view)
    below, count = {}, {}
    for p in data["properties"]:
        count[p["of"]] = count.get(p["of"], 0) + 1
    for name, n in nodes.items():
        up = n["inside"]
        while up in nodes:
            below[up] = below.get(up, 0) + 1
            up = nodes[up]["inside"]
    lines = []
    for name, n in nodes.items():
        depth, up = 0, n["inside"]
        while up in nodes:
            depth, up = depth + 1, nodes[up]["inside"]
        values = "; ".join(_value_text(p) for p in data["properties"] if p["of"] == name)
        line = (f"{'  ' * depth}{name} [{n['detail']}, {n['form']}, {n['shape']}; {below.get(name, 0)} parts inside, "
                f"{count.get(name, 0)} values] {n['what'][:100]}"
                + (f" | {values}" if values else "") + (f" | with: {', '.join(contents[name])}" if name in contents else ""))
        lines.append(line)
    return "\n".join(lines)


def _relations_text(data, names):
    lines = [f"  {r['subject']} {r['relation'].replace('_', ' ')} {r['object']}"
             + (f" x{r['count']}" if r.get("count") else "") + f" [{', '.join(r['claims'])}]"
             for r in data["relations"] if not r.get("nesting") and r["subject"] in names and r["object"] in names]
    return "\n".join(lines) or "  none"


LEVEL_RULES = """For every part of the tree a level and a short reason. exact: shape, size, position and material \
right. simplified: right outer shape, mass and material. lumped: right total mass and material in a simple volume. \
The sensitive parts and what is next to them or shields them are exact (the vessel or holder around the sensitive \
volume, the closest shields, electrodes and reflectors inside it). Large structures further away (outer shields, \
tanks, frames that carry load, mirrors, weights) are simplified. Small parts that matter only by their mass and \
material (cables, screws, connectors, electronics) are lumped. The graph's mark (sensitive, main_structure, \
small_part) is a first guess and can be wrong.
"""


SPLIT_PROMPT = """You plan how the Geant4 geometry model of the detector {detector} is built. What the parts are and where \
they sit is settled: below is the geometry view of the detector graph, every part that will be a volume, as a tree \
(indented = inside the part above), with the values the documents give and the ids of their claims. Do not change the \
tree. Plan the work:

1. Teams. Cut the tree into subsystems, each built by one team. A team is given by its root parts: it builds each \
root and everything inside it, except what is inside the root of another team. Cut where the documents themselves \
describe a subsystem (a shield, a cryostat, a detector array, a readout plane, a support structure), so that each team \
builds into the space that the team outside it leaves. Every outermost part must be the root of a team. A team is \
a subsystem with a real amount of work: several parts built as one unit. A single part with nothing inside it is not a \
team; it stays with the team of the part it is in. Use as few teams as the subsystems of the detector need: a small \
detector, or one that is a single subsystem, is one team, and a large one rarely needs more than a handful. Cut \
where the work is: a part with many parts inside it and many values is split into its subsystems, while parts that \
the documents only mention as surroundings, with few parts and values, go together or with the team of the part \
around them. Many identical modules are built by one team, never one team each.
2. Repeated parts. A part the detector has many of (identical modules, sensors, strings, crystals) is built once and \
placed many times. Name each one with its count and the ids of the claims that give the count.
3. Objections. Where an entry of the graph is wrong and a claim shows it (a part inside the wrong container, two \
parts that are the same, a value on the wrong part), write it down with the claim id. Not what is merely missing.

The tree (name [graph mark, form, shape; kept parts inside it, values it has] what it is | values [claims] | collapsed contents):
{tree}

Other relations between the parts [claims]:
{relations}

The claims cited above (id | claim | source):
{claims}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def _claim_numbers(claim):
    return ([float(claim.value)] if isinstance(claim.value, (int, float)) else numbers_in(str(claim.value))) \
        + numbers_in(claim.statement or "") + numbers_in(claim.quote or "")


def split_check(nodes, split, by_id):
    """What is wrong with a split, as sentences for the model."""
    problems, owner = [], {}
    names = [t.name for t in split.teams]
    if not split.teams:
        problems.append("there is no team")
    for name in set(names):
        if names.count(name) > 1:
            problems.append(f"two teams are called '{name}'")
    for team in split.teams:
        if not team.roots:
            problems.append(f"team {team.name} has no root part")
        for root in team.roots:
            if root not in nodes:
                problems.append(f"team {team.name}: '{root}' is not a part of the tree")
            elif root in owner:
                problems.append(f"'{root}' is a root of both {owner[root]} and {team.name}")
            else:
                owner[root] = team.name
    for name, n in nodes.items():
        if n["inside"] not in nodes and name not in owner:
            problems.append(f"{name} is an outermost part and must be the root of a team")
    if not problems and len(split.teams) > 1:
        team_of = owners(nodes, split)
        for team in split.teams:
            parts = [name for name, t in team_of.items() if t == team.name]
            if len(parts) == 1 and nodes[parts[0]]["inside"] in nodes:     # the outermost part alone holds the teams together
                problems.append(f"team {team.name} builds only {parts[0]}. A single part is not a team: give it to the "
                                "team of the part it is in, or give this team more of the parts around it")
    for r in split.repeats:
        if r.part not in nodes:
            problems.append(f"repeat: '{r.part}' is not a part of the tree")
        elif r.count < 2:
            problems.append(f"repeat {r.part}: a count below 2 is not a repeat")
        elif not r.claims or any(i not in by_id for i in r.claims):
            problems.append(f"repeat {r.part}: give the ids of existing claims")
        elif not any(abs(x - r.count) < 1e-9 for i in r.claims for x in _claim_numbers(by_id[i])):
            problems.append(f"repeat {r.part}: none of the claims {', '.join(r.claims)} gives the count {r.count}")
    for o in split.objections:
        cited = re.findall(r"\b[A-Z]+\d+\b", f"{o.entry} {o.problem}")
        if not cited or any(i not in by_id for i in cited):
            problems.append(f"objection '{o.entry}': cite the id of an existing claim that shows the problem")
    return problems


LEVELS_PROMPT = """You plan how the Geant4 geometry model of the detector {detector} is built. What the parts are and where \
they sit is settled: below is the geometry view of the detector graph, every part that will be a volume, as a tree \
(indented = inside the part above), with the values the documents give. Set the detail level of each part:

""" + LEVEL_RULES + """
The tree (name [graph mark, form, shape; kept parts inside it, values it has] what it is | values [claims] | collapsed contents):
{tree}

Other relations between the parts [claims]:
{relations}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def level_check(nodes, answer):
    problems = [f"'{e.part}' is not a part of the tree" for e in answer.levels if e.part not in nodes]
    missing = [name for name in nodes if name not in {e.part for e in answer.levels}]
    if missing:
        problems.append("no level for: " + ", ".join(missing[:80]))
    return problems


def owners(nodes, split):
    """{kept part: team}: the team of the nearest root at or above it; 'unassigned' if there is none."""
    root_of = {root: t.name for t in split.teams for root in t.roots if root in nodes}
    found = {}
    for name in nodes:
        up = name
        while up in nodes and up not in root_of:
            up = nodes[up]["inside"]
        found[name] = root_of.get(up, "unassigned")
    return found


def boundaries(nodes, team_of):
    """Where a team builds into a part of another team: [{id, outer, outer_team, inner_team, inner: [roots]}]."""
    found = {}
    for name, n in nodes.items():
        outer = n["inside"]
        if outer in nodes and team_of[outer] != team_of[name]:
            found.setdefault((outer, team_of[name]), []).append(name)
    return [{"id": f"I{i}", "outer": outer, "outer_team": team_of[outer], "inner_team": team, "inner": inner}
            for i, ((outer, team), inner) in enumerate(found.items(), 1)]


INTERFACE_PROMPT = """You plan how the Geant4 geometry model of the detector {detector} is built by several teams. Where a \
team builds its parts into a part of another team, the two meet at an interface. The outer team owns it and leaves a \
space; the inner team builds into that space and nowhere else. Write the interface for each place below:

- shape: the shape of the space the inner team may fill (the envelope).
- values: the sizes of that space, and the place of the inner parts in it where the documents give it, each a number \
in a length unit; masses, materials, counts and ratings belong to the parts, not here. The envelope is \
the inner size of the outer part where the documents give that; otherwise the outer size of the inner parts. Each value \
with the ids of the claims it comes from, as the claims state it. A value worked out from the claims (inner diameter = \
outer diameter - 2 x wall) is marked derived, with the reasoning. A size that is needed and that the documents do not \
give is open: value null, and say what is missing.
- placement: where the inner parts sit in the envelope as the documents say (centred, on the floor, hanging from the \
lid), or '' if they do not say.

The places (outer part, owned by the outer team, and the inner parts that are built into it):
{places}

The relations between these parts [claims]:
{relations}

The claims cited above (id | claim | source):
{claims}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def _part_text(data, n):
    values = "; ".join(_value_text(p) for p in data["properties"] if p["of"] == n["name"]) or "no values"
    return f"{n['name']} [{n['form']}, {n['shape']}] {n['what'][:100]} | {values}"


def interface_check(places, answer, by_id):
    """What is wrong with the interfaces, as sentences for the model."""
    problems = []
    ids = [i.id for i in answer.interfaces]
    for place in places:
        if ids.count(place["id"]) != 1:
            problems.append(f"interface {place['id']} needs exactly one entry, it has {ids.count(place['id'])}")
    for i in answer.interfaces:
        if i.id not in {p["id"] for p in places}:
            problems.append(f"'{i.id}' is not one of the places")
        if not i.values:
            problems.append(f"interface {i.id}: give at least one value, or mark the needed sizes open")
        for v in i.values:
            where = f"interface {i.id}, {v.quantity}"
            if v.open:
                if v.value not in (None, ""):
                    problems.append(f"{where}: an open value has value null")
                continue
            if v.value in (None, ""):
                problems.append(f"{where}: a value that is not open needs a value")
            elif not isinstance(v.value, (int, float)) or v.unit.strip() not in LENGTHS:
                problems.append(f"{where}: an envelope value is a size or a position, a number in a length unit "
                                f"({', '.join(LENGTHS)}); a mass, a material, a count or a rating belongs to the parts, not the interface")
            if not v.claims or any(c not in by_id for c in v.claims):
                problems.append(f"{where}: give the ids of existing claims, or mark it open")
            elif v.derived:
                if not v.reasoning:
                    problems.append(f"{where}: a derived value needs its reasoning")
            else:
                numbers = [float(v.value)] if isinstance(v.value, (int, float)) else numbers_in(str(v.value or ""))
                stated = [x for c in v.claims for x in _claim_numbers(by_id[c])]
                if numbers and not any(abs(a - b) <= 1e-9 * max(abs(b), 1) for a in numbers for b in stated):
                    problems.append(f"{where}: {v.value} is not stated by {', '.join(v.claims)}; "
                                    "mark it derived with the reasoning, or take the value the claim states")
    return problems


def make_tasks(data, nodes, contents, team_of, split, levels, places, split_problems=()):
    """One task per kept part, from the outside in: what the piece is, what it can rely on, how it is checked, what is
    missing. Collapsed parts are the content of the piece they are in."""
    chosen = {e.part: e.level for e in levels}
    repeats = {r.part: r for r in split.repeats if not any(p.startswith(f"repeat {r.part}") or p.startswith(f"repeat: '{r.part}'")
                                                            for p in split_problems)}
    interface_of = {root: place["id"] for place in places for root in place["inner"]}
    found, levels = [], {}
    for name, n in nodes.items():
        level = chosen.get(name) or LEVEL.get(n["detail"], "simplified")
        if n["form"] == "filling" and n["inside"] in levels:      # a filling takes the shape of its vessel and its level
            level = levels[n["inside"]]
        levels[name] = level
        values = [p for p in data["properties"] if p["of"] == name]
        held = [p for p in values if p["quantity"] in HELD_BACK and level != "lumped"]
        relations = [r for r in data["relations"] if not r.get("nesting") and name in (r["subject"], r["object"])
                     and r["subject"] in nodes and r["object"] in nodes]
        if n["form"] == "filling":
            gaps = [g for g in n["unknown"] if g == "material"]
        elif level == "lumped":
            gaps = [g for g in n["unknown"] if g == "material"] + ([] if any(p["quantity"] == "mass" for p in values) else ["mass"])
        else:
            gaps = list(n["unknown"])
        found.append({
            "part": name, "team": team_of[name], "level": level, "inside": n["inside"], "form": n["form"], "shape": n["shape"],
            "what": n["what"], "repeat": repeats[name].count if name in repeats else None,
            "contents": contents.get(name, []), "interface": interface_of.get(name),
            "after": n["inside"] if n["inside"] in nodes else None,
            "checks": [{k: p[k] for k in ("quantity", "which", "value", "unit", "claims")} for p in values if p not in held]
                      + [{k: r[k] for k in ("subject", "relation", "object", "count", "claims")} for r in relations],
            "held_back": [{k: p[k] for k in ("quantity", "which", "value", "unit", "claims")} for p in held],
            "gaps": [{"what": g, "effort": EFFORT[level]} for g in gaps],
            "claims": sorted(set(n["claims"]) | {i for p in values for i in p["claims"]} | {i for r in relations for i in r["claims"]},
                             key=lambda i: (len(i), i))})
    return found


def score(plan):
    """What a program can tell about a plan. It does not tell whether the cuts and the envelopes are sensible."""
    values = [v for i in plan["interfaces"] for v in i.get("values", [])]
    return {"kept": len(plan["tasks"]), "teams": len(plan["teams"]),
            "unassigned": sum(t["team"] == "unassigned" for t in plan["tasks"]),
            "interfaces": len(plan["interfaces"]), "unanswered": sum(not i.get("values") for i in plan["interfaces"]),
            "values": len(values), "open": sum(v["open"] for v in values), "derived": sum(v["derived"] for v in values),
            "problems_left": sum(len(rounds[-1]) for rounds in plan["rounds"].values()),
            "exact": sum(t["level"] == "exact" for t in plan["tasks"]), "lumped": sum(t["level"] == "lumped" for t in plan["tasks"]),
            "repeats": sum(t["repeat"] is not None for t in plan["tasks"]),
            "checks": sum(len(t["checks"]) for t in plan["tasks"]), "held_back": sum(len(t["held_back"]) for t in plan["tasks"]),
            "gaps": sum(len(t["gaps"]) for t in plan["tasks"]), "objections": len(plan["objections"])}


def plan_as_text(plan):
    """The build plan as text to look at."""
    s = plan["score"]
    lines = [f"Build plan of {plan['detector']}: {s['kept']} parts, {s['teams']} teams, {s['interfaces']} interfaces "
             f"({s['values']} values, {s['open']} open), {s['exact']} exact, {s['lumped']} lumped, {s['repeats']} repeated, "
             f"{s['gaps']} gaps, {s['problems_left']} problems left", ""]
    tasks = {t["part"]: t for t in plan["tasks"]}
    for team in plan["teams"]:
        lines.append(f"TEAM {team['name']}  roots: {', '.join(team['roots'])}" + (f"  ({team['why']})" if team["why"] else ""))
        for name in team["parts"]:
            t = tasks[name]
            flags = [t["level"]] + ([f"x{t['repeat']}"] if t["repeat"] else []) + ([f"into {t['interface']}"] if t["interface"] else [])
            lines.append(f"  {name} [{', '.join(flags)}] in {t['inside']}: {len(t['checks'])} checks"
                         + (f", held back: {', '.join(h['quantity'] for h in t['held_back'])}" if t["held_back"] else "")
                         + (f", gaps: {', '.join(g['what'] for g in t['gaps'])}" if t["gaps"] else "")
                         + (f", with: {', '.join(t['contents'])}" if t["contents"] else ""))
        lines.append("")
    for i in plan["interfaces"]:
        lines.append(f"INTERFACE {i['id']}: {i['inner_team']} builds {', '.join(i['inner'])} into {i['outer']} "
                     f"(owner {i['outer_team']}); envelope {i.get('shape', '?')}" + (f"; {i['placement']}" if i.get("placement") else ""))
        for v in i.get("values", []):
            lines.append(f"    {v['quantity']}: " + (f"OPEN ({v['note']})" if v["open"] else
                         f"{v['value']} {v['unit']} [{', '.join(v['claims'])}]" + (f" derived: {v['reasoning']}" if v["derived"] else "")))
    if plan["between_teams"]:
        lines += ["", "Relations between teams (for Integrate):"] + [
            f"  {r['subject']} {r['relation'].replace('_', ' ')} {r['object']}" for r in plan["between_teams"]]
    if plan["levels"]:
        lines += ["", "Levels other than the graph's mark gives:"] + [f"  {e['part']} ({e['mark']}) -> {e['level']}: {e['why']}"
                                                                       for e in plan["levels"]]
    if plan.get("graph_answers"):
        record = plan["graph_answers"]
        lines += ["", "Objections of the first plan, and the graph builder's answers:"]
        for i, o in enumerate(record["objections"], 1):
            a = next((a for a in record["answers"] if a["objection"] == i), None)
            lines.append(f"  {o['entry']}: {o['problem']}")
            lines.append("    -> no answer" if a is None else
                         f"    -> {a['decision']}" + (f" ({a['change']} {a['part']} {a['to'] or a['quantity']}; "
                                                      f"{'made' if a['made'] else 'not made'})" if a["decision"] == "change" else "")
                         + f": {a['why']}")
    if plan["objections"]:
        lines += ["", "Objections to the graph" + (" (second plan, not sent)" if plan.get("graph_answers") else "") + ":"] \
            + [f"  {o['entry']}: {o['problem']}" for o in plan["objections"]]
    return "\n".join(lines)


def _claims_text(claims, ids):
    return "\n".join(c.line() for c in claims if c.id in ids) or "  none"


def build_plan(data, view, claims, detector, log=None, model=PLAN_MODEL):
    """The build plan of the kept parts of a graph. `claims` are the accepted claims of the graph."""
    by_id = {c.id: c for c in claims}
    nodes, contents = kept_tree(data, view)
    cited = {i for n in nodes.values() for i in n["claims"]} | {i for p in data["properties"] if p["of"] in nodes for i in p["claims"]} \
        | {i for r in data["relations"] if r["subject"] in nodes and r["object"] in nodes for i in r["claims"]}
    request = SPLIT_PROMPT.format(detector=detector, tree=_tree_text(data, view), relations=_relations_text(data, nodes),
                                  claims=_claims_text(claims, cited), schema=json.dumps(Split.model_json_schema(), separators=(",", ":")))
    try:
        split, split_rounds = D._with_repairs(model, [{"role": "user", "content": request}], Split,
                                              lambda s: split_check(nodes, s, by_id), log, "coordinator_split")
    except ValueError as error:
        split, split_rounds = Split(teams=[]), [[f"no usable answer: {str(error)[:200]}"]]
    if not split.teams:                  # without a usable split the detector is one team
        split.teams = [Team(name="detector", roots=[n for n, x in nodes.items() if x["inside"] not in nodes], why="no usable split")]
    request = LEVELS_PROMPT.format(detector=detector, tree=_tree_text(data, view), relations=_relations_text(data, nodes),
                                   schema=json.dumps(Levels.model_json_schema(), separators=(",", ":")))
    try:
        answer, level_rounds = D._with_repairs(model, [{"role": "user", "content": request}], Levels,
                                               lambda a: level_check(nodes, a), log, "coordinator_levels")
        levels = [e for e in answer.levels if e.part in nodes]
    except ValueError as error:          # without an answer each part keeps the level its mark gives
        levels, level_rounds = [], [[f"no usable answer: {str(error)[:200]}"]]
    team_of = owners(nodes, split)
    places = boundaries(nodes, team_of)
    answers, interface_rounds = {}, [[]]
    if places:
        listing = "\n\n".join(f"{p['id']}: the team {p['inner_team']} builds into {p['outer']} (team {p['outer_team']})\n"
                              f"  outer: {_part_text(data, nodes[p['outer']])}\n"
                              + "\n".join(f"  inner: {_part_text(data, nodes[r])}" for r in p["inner"]) for p in places)
        ends = {p["outer"] for p in places} | {r for p in places for r in p["inner"]}
        ids = {i for name in ends for i in nodes[name]["claims"]} | {i for p in data["properties"] if p["of"] in ends for i in p["claims"]} \
            | {i for r in data["relations"] if r["subject"] in ends and r["object"] in ends for i in r["claims"]}
        request = INTERFACE_PROMPT.format(detector=detector, places=listing, relations=_relations_text(data, ends),
                                          claims=_claims_text(claims, ids),
                                          schema=json.dumps(Interfaces.model_json_schema(), separators=(",", ":")))
        try:
            answer, interface_rounds = D._with_repairs(model, [{"role": "user", "content": request}], Interfaces,
                                                       lambda a: interface_check(places, a, by_id), log, "coordinator_interfaces")
            answers = {i.id: i for i in answer.interfaces}
        except ValueError as error:
            interface_rounds = [[f"no usable answer: {str(error)[:200]}"]]
    tasks = make_tasks(data, nodes, contents, team_of, split, levels, places, split_rounds[-1])
    teams = [{"name": t.name, "roots": [r for r in t.roots if r in nodes], "why": t.why,
              "parts": [x["part"] for x in tasks if x["team"] == t.name]} for t in split.teams]
    if any(x["team"] == "unassigned" for x in tasks):
        teams.append({"name": "unassigned", "roots": [], "why": "parts under no root", "parts": [x["part"] for x in tasks if x["team"] == "unassigned"]})
    first = {name: i for i, name in enumerate(nodes)}
    teams.sort(key=lambda t: min((first[p] for p in t["parts"]), default=len(first)))
    plan = {"detector": detector, "teams": teams,
            "levels": [{**e.model_dump(), "mark": nodes[e.part]["detail"]} for e in levels if e.part in nodes
                       and e.level != LEVEL.get(nodes[e.part]["detail"])],
            "repeats": [r.model_dump() for r in split.repeats if any(t["part"] == r.part and t["repeat"] for t in tasks)],
            "objections": [o.model_dump() for o in split.objections],
            "interfaces": [{**p, **({k: v for k, v in answers[p["id"]].model_dump().items() if k != "id"} if p["id"] in answers else {})}
                           for p in places],
            "between_teams": [{k: r[k] for k in ("subject", "relation", "object", "claims")} for r in data["relations"]
                              if not r.get("nesting") and r["subject"] in nodes and r["object"] in nodes
                              and team_of[r["subject"]] != team_of[r["object"]]],
            "tasks": tasks, "rounds": {"split": split_rounds, "levels": level_rounds, "interfaces": interface_rounds}}
    plan["score"] = score(plan)
    return plan


def coordinate(folder, detector, log=None, model=PLAN_MODEL, objections=True, out=None):
    """The coordinator on the graph in `folder`: plan; if it objects to the graph, the graph builder answers and the
    plan is made once more on the graph it returns. The second plan's objections are kept, not sent again.
    Writes build_plan.json and .txt (and the answered graph and view) into `out` (default: `folder`)."""
    folder = Path(folder)
    out = Path(out or folder)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads((folder / "detector_graph.json").read_text())
    view = json.loads((folder / "geometry_view.json").read_text())
    claims = [c for c in C.load(folder) if c.status == "accepted"]
    plan = build_plan(data, view, claims, detector, log, model)
    if objections and plan["objections"]:
        first = plan
        data, view, record = D.answer_objections(folder, detector, [(o["entry"], o["problem"]) for o in plan["objections"]], view, log)
        (out / "detector_graph_answered.json").write_text(json.dumps(data, indent=1))
        (out / "detector_graph_answered.txt").write_text(D.as_text(data) + "\n")
        (out / "geometry_view_answered.json").write_text(json.dumps(view, indent=1))
        plan = build_plan(data, view, claims, detector, log, model)
        plan["first_plan"] = {k: first[k] for k in ("teams", "objections", "score")}
        plan["graph_answers"] = record
    (out / "build_plan.json").write_text(json.dumps(plan, indent=1))
    (out / "build_plan.txt").write_text(plan_as_text(plan) + "\n")
    return plan


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    print(plan_as_text(coordinate(args[0], name)))
