"""Check the arrangement of a built geometry against the layout plan. A program, no LLM.

The plan says what is inside what and how parts are arranged. The builder says
which volume stands for which part. This module measures, in Geant4's report of
the geometry, whether each statement holds.
"""

import re

TOLERANCE = 1e-6


def placed(report):
    """Every placed volume with its place in the world: [{volume, ancestors, lo, hi, centre}].

    Rotations are ignored: a rotated part is treated as if it stood upright.
    """
    known, found = {}, []
    for part in report.get("parts", []):
        mother = known.get(part["mother"])
        centre = [p + (mother["centre"][i] if mother else 0.0) for i, p in enumerate(part["position_mm"])]
        half = [s / 2 for s in part.get("size_mm", [0, 0, 0])]
        entry = {"volume": part["volume"], "ancestors": (mother["ancestors"] + [mother["volume"]]) if mother else [],
                 "centre": centre, "lo": [c - h for c, h in zip(centre, half)], "hi": [c + h for c, h in zip(centre, half)]}
        known[part["volume"]] = entry
        found.append(entry)
    return found


def _of(volumes, name):
    """The placed volumes called `name`, or whose name is `name` plus a number."""
    exact = [v for v in volumes if v["volume"] == name]
    return exact or [v for v in volumes if re.fullmatch(re.escape(name) + r"[_\-]?\d+(_\d+)*", v["volume"])]


def _within(a, b, axes=(0, 1, 2)):
    return all(a["lo"][i] >= b["lo"][i] - TOLERANCE and a["hi"][i] <= b["hi"][i] + TOLERANCE for i in axes)


def _holds(relation, a, b):
    """Does `relation` hold for one placed volume a against one placed volume b?"""
    descends = b["volume"] in a["ancestors"]
    height = b["hi"][2] - b["lo"][2]
    if relation == "inside":
        return descends or _within(a, b)
    if relation == "surrounds":           # a is around b: b lies within a sideways, and they share a height range
        return a["volume"] in b["ancestors"] or (_within(b, a, (0, 1)) and b["lo"][2] < a["hi"][2] and b["hi"][2] > a["lo"][2])
    if relation == "centred_in":
        return all(abs(a["centre"][i] - b["centre"][i]) <= 0.02 * max(b["hi"][i] - b["lo"][i], 1.0) for i in (0, 1))
    if relation == "at_bottom_of":
        return a["centre"][2] <= b["lo"][2] + height / 3
    if relation == "at_top_of":
        return a["centre"][2] >= b["hi"][2] - height / 3
    if relation == "outside":
        return not descends and not _within(a, b)
    raise ValueError(relation)


def check_relations(plan, volume_of, report):
    """One row per statement of the plan: {"what", "status", "why"}.

    plan       the Coordinator's Plan
    volume_of  {part name: volume name}, from the builder's notes
    status     "met", "not met" or "not shown" (the builder named no volume for one of the two parts)
    """
    volumes, rows = placed(report), []
    statements = [(p.name, "inside", p.inside) for p in plan.parts if p.inside != "world"]
    statements += [(r.part, r.relation, r.other) for r in plan.relations]
    for part, relation, other in dict.fromkeys(statements):
        what = f"{part} {relation.replace('_', ' ')} {other}"
        names = volume_of.get(part), volume_of.get(other)
        if not all(names):
            rows.append({"what": what, "status": "not shown", "why": "no volume named for "
                         + " and ".join(n for n, v in zip((part, other), names) if not v)})
            continue
        a, b = _of(volumes, names[0]), _of(volumes, names[1])
        if not a or not b:
            missing = " and ".join(f"'{n}'" for n, v in zip(names, (a, b)) if not v)
            rows.append({"what": what, "status": "not met", "why": f"there is no volume {missing}"})
            continue
        # every copy of the part must stand in the relation to some copy of the other
        fails = [x["volume"] for x in a if not any(_holds(relation, x, y) for y in b)]
        rows.append({"what": what, "status": "not met" if fails else "met",
                     "why": f"not true for {', '.join(fails[:4])}{' and more' if len(fails) > 4 else ''}" if fails else ""})
    return rows


def as_feedback(rows):
    """The statements that are not met, as text for the builder. Empty if there are none."""
    return "\n".join(f"- {row['what']}: {row['why']}" for row in rows if row["status"] == "not met")
