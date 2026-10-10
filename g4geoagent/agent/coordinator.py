"""Coordinator: decides the layout of the whole detector before anything is built.

From the parts and the agreed claims it writes one plan: what sits inside what,
which parts are hollow, how detailed each part is to be, how parts are arranged
relative to each other, and which team builds which parts. The teams build from
this plan, and programs check the result against it.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from g4geoagent.agent.llm import call_llm_json

MODEL = "lbl/gpt-oss-120b"
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
