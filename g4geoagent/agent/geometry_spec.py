"""The geometry specification a team writes, and the program that turns it into a Geant4 geometry.

A team does not write Geant4 code. It writes a specification: the solids (primitives, profiles, booleans), the
volumes made of them, each with a material and a place, grouped by the part of the detector they build. Every number
says where it comes from, in this order of preference (agreed with the user 2026-10-14):

    stated                  in the text of a document, with the claim ids
    written_in_figure       a number written in a figure (a dimension label), with the claim ids
    derived                 worked out from other numbers by a rule, which is given
    researched              from a source found by research, with the claim ids
    measured_from_figure    measured off a figure by a program, only when nothing above exists
    estimated               a judgement, with the reasoning

`check` tests a specification against the team's brief (every part built or left out with a reason, every stated
number equal to a number of its claims, materials known, solids valid). `to_gdml` writes the GDML file; Geant4 then
loads it, checks overlaps and gives the mass of every volume (inspector/geant4_run.py).
"""

import math
import re
from typing import Literal

from pydantic import BaseModel, Field

ORIGINS = ("stated", "written_in_figure", "derived", "researched", "measured_from_figure", "estimated")
CITED = ("stated", "written_in_figure", "researched")
LENGTH = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 1e-3, "μm": 1e-3, "in": 25.4, "inch": 25.4}
ANGLE = {"deg": math.pi / 180, "rad": 1.0}
BLOCKS = ("cylinder", "hollow_cylinder", "cup")      # building blocks, expanded by the program into profiles
KINDS = ("cylinder", "hollow_cylinder", "cup", "tube", "cone", "box", "sphere", "torus", "polycone", "polyhedra", "extrusion", "union", "subtraction", "intersection")
PARAMS = {   # what each kind needs; lengths are full lengths, angles default to a full turn
    "cylinder": ("radius", "height"),                       # a solid cylinder or disk
    "hollow_cylinder": ("outer_radius", "wall", "height"),  # a tube or ring, open at both ends
    "cup": ("outer_radius", "wall", "bottom", "height"),    # a hollow cylinder closed at one end (param 'open': top or bottom)
    "tube": ("rmin", "rmax", "length"),
    "cone": ("rmin1", "rmax1", "rmin2", "rmax2", "length"),
    "box": ("x", "y", "z"),
    "sphere": ("rmin", "rmax"),
    "torus": ("rmin", "rmax", "rtor"),
    "polycone": (),
    "polyhedra": ("sides",),
    "extrusion": ("thickness",),
}


class Num(BaseModel):
    value: float
    unit: str = Field(description="mm, cm, m for lengths; deg for angles; '' for a count")
    origin: Literal["stated", "written_in_figure", "derived", "researched", "measured_from_figure", "estimated"]
    claims: list[str] = Field(default_factory=list, description="ids of the claims it rests on (stated, written_in_figure, researched, derived)")
    why: str = Field(default="", description="for derived: the rule; for estimated and measured: the reasoning")


class Point(BaseModel):
    z: Num
    rmin: Num
    rmax: Num


class Corner(BaseModel):
    x: Num
    y: Num


class Solid(BaseModel):
    name: str
    kind: Literal["cylinder", "hollow_cylinder", "cup", "tube", "cone", "box", "sphere", "torus", "polycone", "polyhedra",
                  "extrusion", "union", "subtraction", "intersection"]
    open: Literal["top", "bottom"] = Field(default="top", description="cup: the open end")
    params: dict[str, Num] = Field(default_factory=dict, description="the numbers the kind needs, see the list")
    points: list[Point] = Field(default_factory=list, description="polycone, polyhedra: the profile from bottom to top")
    corners: list[Corner] = Field(default_factory=list, description="extrusion: the outline in the x-y plane")
    first: str = Field(default="", description="boolean: the name of the first solid")
    second: str = Field(default="", description="boolean: the name of the second solid")
    position: list[Num] = Field(default_factory=list, description="boolean: x, y, z of the second solid relative to the first")
    rotation: list[Num] = Field(default_factory=list, description="boolean: rotation of the second solid about x, y, z")


class Volume(BaseModel):
    name: str
    part: str = Field(description="the part of the brief it belongs to")
    solid: str
    material: str = Field(description="a common name ('lead', 'copper', 'stainless steel') or a Geant4 name (G4_Pb)")
    material_origin: Literal["stated", "written_in_figure", "derived", "researched", "measured_from_figure", "estimated"]
    material_claims: list[str] = Field(default_factory=list)
    inside: str = Field(default="team", description="'team' (the team's own frame) or another volume of this specification")
    position: list[Num] = Field(default_factory=list, description="x, y, z of its centre in the volume it is inside")
    rotation: list[Num] = Field(default_factory=list, description="rotation about x, y, z")


class MaterialDef(BaseModel):
    name: str
    density: Num = Field(description="in g/cm3")
    formula: dict[str, int] = Field(description="atoms per molecule, by element symbol: {'H': 3, 'B': 1, 'O': 3}")


class LeftOut(BaseModel):
    part: str
    why: str


class TeamSpec(BaseModel):
    materials: list[MaterialDef] = Field(default_factory=list, description="materials not known by name: density and formula")
    solids: list[Solid]
    volumes: list[Volume]
    left_out: list[LeftOut] = Field(default_factory=list, description="parts of the brief not built, with the reason")
    questions: list[str] = Field(default_factory=list, description="for the Coordinator: conflicts, parts that seem wrongly assigned")
    shapes: list[str] = Field(default_factory=list, description="for each part: the shape chosen and what it rests on (claim, figure)")


def _numbers(spec):
    """Every number of a specification, with where it is."""
    for s in spec.solids:
        for key, n in s.params.items():
            yield f"solid {s.name}: {key}", n
        for i, p in enumerate(s.points):
            for key in ("z", "rmin", "rmax"):
                yield f"solid {s.name}: point {i} {key}", getattr(p, key)
        for i, c in enumerate(s.corners):
            yield f"solid {s.name}: corner {i} x", c.x
            yield f"solid {s.name}: corner {i} y", c.y
        for i, n in enumerate(s.position + s.rotation):
            yield f"solid {s.name}: placement {i}", n
    for v in spec.volumes:
        for i, n in enumerate(v.position + v.rotation):
            yield f"volume {v.name}: placement {i}", n
    for m in spec.materials:
        yield f"material {m.name}: density", m.density


def _in_mm(n):
    return n.value * LENGTH.get(n.unit.strip().lower(), 1.0)


def check(spec, brief, claims, known_material):
    """What is wrong with a specification, as sentences for the model. `brief` is the team's input (team_walk.py),
    `claims` {id: Claim}, `known_material(name)` tells whether a material name can be made."""
    problems = []
    names = {s.name for s in spec.solids}
    for s in spec.solids:
        if s.kind in ("union", "subtraction", "intersection"):
            for other in (s.first, s.second):
                if other not in names or other == s.name:
                    problems.append(f"solid {s.name}: boolean of '{other}', which is not another solid of the specification")
        elif s.kind in ("polycone", "polyhedra"):
            if len(s.points) < 2:
                problems.append(f"solid {s.name}: a {s.kind} needs at least two points of its profile")
            for i, p in enumerate(s.points):
                if _in_mm(p.rmin) > _in_mm(p.rmax) or _in_mm(p.rmin) < 0:
                    problems.append(f"solid {s.name}: point {i} has rmin {p.rmin.value} {p.rmin.unit} above rmax {p.rmax.value} {p.rmax.unit}")
            zs = [_in_mm(p.z) for p in s.points]
            if any(b < a for a, b in zip(zs, zs[1:])):
                problems.append(f"solid {s.name}: the profile must go from bottom to top (z never decreasing)")
        elif s.kind == "extrusion" and len(s.corners) < 3:
            problems.append(f"solid {s.name}: an extrusion needs at least three corners")
        for key in PARAMS.get(s.kind, ()):
            if key not in s.params:
                problems.append(f"solid {s.name}: a {s.kind} needs '{key}'")
        p = {k: _in_mm(v) for k, v in s.params.items()}
        if s.kind in ("hollow_cylinder", "cup") and "wall" in p and "outer_radius" in p and p["wall"] >= p["outer_radius"]:
            problems.append(f"solid {s.name}: the wall is as thick as the outer radius; use a cylinder for a solid part")
        if s.kind == "cup" and {"bottom", "height"} <= set(p) and p["bottom"] >= p["height"]:
            problems.append(f"solid {s.name}: the bottom is as thick as the cup is high; use a cylinder for a solid part")
        if s.kind in ("tube", "sphere") and p.get("rmin", 0) >= p.get("rmax", 1):
            problems.append(f"solid {s.name}: rmin must be below rmax")
        if any(v <= 0 for k, v in p.items() if k in ("length", "x", "y", "z", "rmax", "thickness", "radius", "outer_radius", "wall", "height", "bottom")):
            problems.append(f"solid {s.name}: a length is zero or negative")
    for where, n in _numbers(spec):
        if n.origin in CITED or (n.origin == "derived" and not n.why):
            if n.origin in CITED and not n.claims:
                problems.append(f"{where} = {n.value} {n.unit} is '{n.origin}' but names no claim")
            elif n.origin == "derived":
                problems.append(f"{where} = {n.value} {n.unit} is derived but gives no rule")
        if n.origin in ("stated", "written_in_figure") and n.claims:
            wanted = [x for i in n.claims if i in claims for x in _claim_numbers(claims[i])]
            if not any(abs(n.value - w) <= 1e-6 * max(abs(w), 1) for w in wanted):
                problems.append(f"{where} = {n.value} {n.unit} is '{n.origin}', but none of {', '.join(n.claims)} states "
                                f"{n.value:g}; use the number the claim states, or another origin")
        if n.origin in ("estimated", "measured_from_figure") and not n.why:
            problems.append(f"{where} = {n.value} {n.unit} is '{n.origin}' and needs its reasoning")
        unknown = [i for i in n.claims if i not in claims]
        if unknown:
            problems.append(f"{where}: unknown claim ids {', '.join(unknown)}")
    volumes = {v.name for v in spec.volumes}
    for v in spec.volumes:
        if v.solid not in names:
            problems.append(f"volume {v.name}: its solid '{v.solid}' is not in the specification")
        if v.inside != "team" and v.inside not in volumes:
            problems.append(f"volume {v.name}: it is inside '{v.inside}', which is not a volume of the specification")
        if v.material not in {m.name for m in spec.materials} and not known_material(v.material):
            problems.append(f"volume {v.name}: material '{v.material}' is not known; use a common name or a Geant4 name, "
                            "or define it under materials with its density and formula")
        if v.material_origin in CITED and not v.material_claims:
            problems.append(f"volume {v.name}: material is '{v.material_origin}' but names no claim")
    parts = {t["part"] for t in brief["tasks"]}
    done = {v.part for v in spec.volumes} | {x.part for x in spec.left_out}
    for part in sorted(parts - done):
        problems.append(f"part {part} of the brief is neither built nor left out with a reason")
    for part in sorted({v.part for v in spec.volumes} - parts):
        problems.append(f"volume of '{part}', which is not a part of the brief")
    return problems


def _claim_numbers(claim):
    from g4geoagent.agent.compare import numbers_in
    if isinstance(claim.value, (int, float)):
        return [float(claim.value)]
    return [float(x) for x in numbers_in(f"{claim.value} {claim.statement}")]


def profile(spec, name):
    """The (z, rmin, rmax) profile in mm of a solid that is round about its axis, bottom to top, centred as Geant4
    centres it; None for other solids."""
    s = next(x for x in spec.solids if x.name == name)
    p = {k: _in_mm(v) for k, v in s.params.items()}
    if s.kind == "cylinder":
        h = p["height"] / 2
        return [(-h, 0.0, p["radius"]), (h, 0.0, p["radius"])]
    if s.kind == "hollow_cylinder":
        h = p["height"] / 2
        return [(-h, p["outer_radius"] - p["wall"], p["outer_radius"]), (h, p["outer_radius"] - p["wall"], p["outer_radius"])]
    if s.kind == "cup":
        h, r, inner, b = p["height"] / 2, p["outer_radius"], p["outer_radius"] - p["wall"], p["bottom"]
        prof = [(-h, 0.0, r), (-h + b, 0.0, r), (-h + b, inner, r), (h, inner, r)]
        return prof if s.open == "top" else [(-z, a, c) for z, a, c in reversed([(-h, 0.0, r), (-h + b, 0.0, r), (-h + b, inner, r), (h, inner, r)])]
    if s.kind in ("polycone", "polyhedra"):
        prof = [(_in_mm(x.z), _in_mm(x.rmin), _in_mm(x.rmax)) for x in s.points]
        middle = (prof[0][0] + prof[-1][0]) / 2 if prof else 0.0
        return [(z - middle, a, b) for z, a, b in prof]       # every solid is centred on its origin
    if s.kind == "tube":
        h = p["length"] / 2
        return [(-h, p["rmin"], p["rmax"]), (h, p["rmin"], p["rmax"])]
    if s.kind == "cone":
        h = p["length"] / 2
        return [(-h, p["rmin1"], p["rmax1"]), (h, p["rmin2"], p["rmax2"])]
    return None


def extents(spec):
    """Where each volume ends up in the team's frame: {volume: (zlow, zhigh, rmax) in mm} for round solids,
    taking the chain of mothers into account."""
    by_name = {v.name: v for v in spec.volumes}

    def offset(v):
        z = _in_mm(v.position[2]) if len(v.position) == 3 else 0.0
        return z + (offset(by_name[v.inside]) if v.inside in by_name else 0.0)
    out = {}
    for v in spec.volumes:
        prof = profile(spec, v.solid)
        if prof:
            dz = offset(v)
            out[v.name] = (prof[0][0] + dz, prof[-1][0] + dz, max(b for _, _, b in prof))
    return out


def to_gdml(spec, path):
    """Write the GDML file of a specification: the team's volumes in a world of vacuum. Returns the registry."""
    import pyg4ometry.gdml as gd
    import pyg4ometry.geant4 as g4

    from g4geoagent.blueprint.materials import material

    reg = g4.Registry()
    made = {}

    def mm(n):
        return _in_mm(n)

    def ang(n):
        return n.value * ANGLE.get(n.unit.strip().lower(), math.pi / 180)

    def solid(name):
        if name in made:
            return made[name]
        s = next(x for x in spec.solids if x.name == name)
        p = s.params
        full = 2 * math.pi
        if s.kind in BLOCKS:
            prof = profile(spec, s.name)
            out = g4.solid.Polycone(s.name, 0, full, [z for z, _, _ in prof], [a for _, a, _ in prof], [c for _, _, c in prof],
                                    reg, "mm", "rad")
        elif s.kind == "tube":
            out = g4.solid.Tubs(s.name, mm(p["rmin"]), mm(p["rmax"]), mm(p["length"]),
                                ang(p["sphi"]) if "sphi" in p else 0, ang(p["dphi"]) if "dphi" in p else full, reg, "mm", "rad")
        elif s.kind == "cone":
            out = g4.solid.Cons(s.name, mm(p["rmin1"]), mm(p["rmax1"]), mm(p["rmin2"]), mm(p["rmax2"]), mm(p["length"]),
                                0, full, reg, "mm", "rad")
        elif s.kind == "box":
            out = g4.solid.Box(s.name, mm(p["x"]), mm(p["y"]), mm(p["z"]), reg, "mm")
        elif s.kind == "sphere":
            out = g4.solid.Sphere(s.name, mm(p["rmin"]), mm(p["rmax"]), 0, full,
                                  ang(p["theta_start"]) if "theta_start" in p else 0,
                                  ang(p["theta_delta"]) if "theta_delta" in p else math.pi, reg, "mm", "rad")
        elif s.kind == "torus":
            out = g4.solid.Torus(s.name, mm(p["rmin"]), mm(p["rmax"]), mm(p["rtor"]), 0, full, reg, "mm", "rad")
        elif s.kind == "polycone":
            prof = profile(spec, s.name)
            out = g4.solid.Polycone(s.name, 0, full, [z for z, _, _ in prof], [a for _, a, _ in prof], [c for _, _, c in prof],
                                    reg, "mm", "rad")
        elif s.kind == "polyhedra":
            prof = profile(spec, s.name)
            out = g4.solid.Polyhedra(s.name, 0, full, int(p["sides"].value), len(prof), [z for z, _, _ in prof],
                                     [a for _, a, _ in prof], [c for _, _, c in prof], reg, "mm", "rad")
        elif s.kind == "extrusion":
            half = mm(p["thickness"]) / 2
            out = g4.solid.ExtrudedSolid(s.name, [[mm(c.x), mm(c.y)] for c in s.corners],
                                         [[-half, [0, 0], 1], [half, [0, 0], 1]], reg, "mm")
        else:
            rotation = [ang(x) for x in s.rotation] or [0, 0, 0]
            position = [mm(x) for x in s.position] or [0, 0, 0]
            make = {"union": g4.solid.Union, "subtraction": g4.solid.Subtraction, "intersection": g4.solid.Intersection}[s.kind]
            out = make(s.name, solid(s.first), solid(s.second), [rotation, position], reg)
        made[name] = out
        return out

    defined = {m.name: m for m in spec.materials}

    def stuff(name):
        if name in defined:
            return material(reg, name, density=defined[name].density.value, formula=defined[name].formula)
        return material(reg, name)

    logical = {}
    for v in spec.volumes:
        logical[v.name] = g4.LogicalVolume(solid(v.solid), stuff(v.material), f"{v.name}_lv", reg)
    extent = max([mm(n) for _, n in _numbers(spec) if n.unit.strip().lower() in LENGTH] + [1000.0])
    world = g4.LogicalVolume(g4.solid.Box("world", 8 * extent, 8 * extent, 8 * extent, reg, "mm"),
                             material(reg, "vacuum"), "world_lv", reg)
    for v in spec.volumes:
        mother = world if v.inside == "team" else logical[v.inside]
        g4.PhysicalVolume([ang(x) for x in v.rotation] or [0, 0, 0], [mm(x) for x in v.position] or [0, 0, 0],
                          logical[v.name], v.name, mother, reg)
    reg.setWorld(world.name)
    writer = gd.Writer()
    writer.addDetector(reg)
    writer.write(str(path))
    return reg


def known_material(name):
    """Can `material` make this name? (A common name, an element, or a Geant4 name.)"""
    import pyg4ometry.geant4 as g4

    from g4geoagent.blueprint.materials import material
    try:
        material(g4.Registry(), name)
        return True
    except Exception:
        return False


def origins(spec):
    """How many numbers of the specification come from where."""
    counts = {o: 0 for o in ORIGINS}
    for _, n in _numbers(spec):
        counts[n.origin] += 1
    return counts


def as_text(spec):
    """The specification as text, one line per number, for the user and for the model's repairs."""
    lines = []
    for s in spec.solids:
        lines.append(f"SOLID {s.name}: {s.kind}" + (f" of {s.first} and {s.second}" if s.first else ""))
        for where, n in _numbers(TeamSpec(solids=[s], volumes=[])):
            lines.append(f"    {where.split(': ', 1)[1]} = {n.value:g} {n.unit}  [{n.origin}{': ' + ', '.join(n.claims) if n.claims else ''}"
                         f"{'; ' + n.why if n.why else ''}]")
    for v in spec.volumes:
        place = ", ".join(f"{n.value:g} {n.unit}" for n in v.position) or "centre"
        lines.append(f"VOLUME {v.name} (part {v.part}): solid {v.solid}, {v.material} [{v.material_origin}"
                     f"{': ' + ', '.join(v.material_claims) if v.material_claims else ''}], inside {v.inside} at {place}")
    for x in spec.left_out:
        lines.append(f"LEFT OUT {x.part}: {x.why}")
    for q in spec.questions:
        lines.append(f"QUESTION: {q}")
    for s in spec.shapes:
        lines.append(f"SHAPE: {s}")
    return "\n".join(lines)
