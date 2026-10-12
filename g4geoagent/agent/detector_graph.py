"""The graph step: a model builds the detector graph from the claims, and a program checks its work.

    python -m g4geoagent.agent.detector_graph <folder with claims.jsonl> [--name "LEGEND-200"]

The model does the judging: which names are one part, which part a value belongs to, what is inside
what, what follows from a statement. The program does the bookkeeping:

    - every entry of the graph names the claims it rests on, and those claims exist;
    - a number in the graph is the number of one of its claims, unless the entry is marked as derived;
    - an edge either rests on a relation claim or is marked as inferred, with its reasoning;
    - every accepted claim is used in the graph or set aside with a reason;
    - the structure is valid: every part has one container, there are no loops.

What fails goes back to the model. What still fails after that is taken out and listed.
"""

import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from g4geoagent.agent import claims as C
from g4geoagent.agent import graph as G
from g4geoagent.agent.compare import numbers_in
from g4geoagent.agent.llm import call_llm_json

MODEL, REVIEWER = "lbl/gpt-oss-120b", "lbl/gemma-4"
REPAIRS = 3


class Node(BaseModel):
    name: str = Field(description="One name for the part, lower case with underscores, singular")
    also_called: list[str] = Field(default_factory=list, description="The other names the claims use for this part")
    what: str = Field(description="One sentence: what it is")
    shape: Literal["cylinder", "tube", "box", "sphere", "plate", "other", "not_stated"] = "not_stated"
    form: Literal["solid", "hollow", "filling"] = Field(
        description="'hollow': a vessel, shell or tube that has other parts or a filling inside. 'filling': the liquid "
                    "or gas that fills a vessel. 'solid': everything else")
    features: list[str] = Field(default_factory=list)
    detail: Literal["sensitive", "main_structure", "small_part"]
    inside: str = Field(description="The name of the part that directly contains it, or 'world' for the outermost part")
    claims: list[str] = Field(description="Ids of the claims that this part, its shape, its features and its container rest on")


class NodeProperty(BaseModel):
    of: str
    quantity: str
    which: str = "not_stated"
    value: float | str
    unit: str = ""
    wording: str = "exact"
    claims: list[str]
    derived: bool = Field(default=False, description="true if the value is worked out from the claims and not stated by one of them")
    reasoning: str = Field(default="", description="For a derived value: how it follows")


class Edge(BaseModel):
    subject: str
    relation: Literal["contains", "surrounds", "encloses", "concentric_with", "at_bottom_of", "at_top_of", "centred_in",
                      "mounted_on", "attached_to", "outside", "consists_of", "next_to"]
    object: str
    count: int | None = None
    claims: list[str]
    inferred: bool = Field(default=False, description="true if no claim states this relation and it follows from other claims")
    reasoning: str = Field(default="", description="For an inferred relation: how it follows")


class SetAside(BaseModel):
    claim: str
    reason: Literal["not_geometry", "other_detector", "not_a_part", "same_as", "contradicted_by"] = Field(
        description="'not_geometry': a voltage, a rate, a performance figure. 'other_detector': about another experiment, "
                    "an earlier version or a prototype. 'not_a_part': a material, a coating, software, a signal. "
                    "'same_as': says what another claim says, which is used in the graph. 'contradicted_by': another claim "
                    "says otherwise and is used in the graph")
    other: str = Field(default="", description="For 'same_as' and 'contradicted_by': the id of the other claim, which must be used in the graph")


class DetectorGraph(BaseModel):
    nodes: list[Node]
    properties: list[NodeProperty]
    edges: list[Edge]
    set_aside: list[SetAside] = Field(default_factory=list)


class Objection(BaseModel):
    entry: str = Field(description="The entry of the graph, e.g. 'liquid_argon: mass = 6 t' or 'nylon_mini_shroud inside world'")
    problem: str = Field(description="What is wrong with it, with the id of the claim that shows it")


class Review(BaseModel):
    objections: list[Objection]


PROMPT = """You build a graph of the detector {detector} from claims. The claims were taken from documents by readers
and each one was checked against its source. A geometry model will be built from your graph, so it must say
what the parts are, what each one is inside of, and how they are arranged.

The claims (id | claim | source):
{claims}

Build the graph:

nodes: one node per physical part.
- The claims use different names for the same part (an abbreviation and its long form, a label from a figure and
  the name in the text, singular and plural). Make them one node and list the other names under also_called.
  Do not join a part with its component, a vessel with its filling, or one item with the array of such items.
- inside: the part that directly contains it. Work from the outside in. A vessel (form 'hollow') contains its
  filling (form 'filling'); what sits in the liquid is inside the filling, not inside the vessel. A part that
  surrounds or encloses other parts is 'hollow'. Only the outermost part is inside 'world'.
- Leave out things that are not parts of the detector: materials, coatings, signals, software, other experiments.

properties: the values of each part: sizes, masses, volumes, counts, and what it is made of (quantity 'material').
A value belongs to the part it measures. Give the number exactly as its claim has it. Every value claim that
describes the construction becomes a property; a claim is never "used" by setting it aside. You may work out a
value from claims (a height from a volume and a diameter); then set derived = true and say how.

edges: how the parts are arranged, beyond 'inside'. Use the relation claims. You may add a relation that no claim
states but that follows from the claims; then set inferred = true and say how it follows.

set_aside: every claim that is not in the graph, with one of the fixed reasons. For 'same_as' and 'contradicted_by'
give the id of the other claim; that claim must itself be in the graph.

Rules
- Every node, property and edge lists the ids of the claims it rests on. Use only ids from the list above.
- Do not add parts, numbers or relations from your own knowledge of this or any other detector.
- Every claim id must appear somewhere: in a node, a property, an edge, or under set_aside.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def check(graph, claims, cover=None):
    """What is wrong with a graph, as sentences for the model. `claims` are the accepted claims;
    `cover` are the ones that must be accounted for (all of them unless given)."""
    by_id = {c.id: c for c in claims}
    names = {n.name for n in graph.nodes}
    problems = []
    for n in graph.nodes:
        if n.inside != "world" and n.inside not in names:
            problems.append(f"node {n.name}: it is inside '{n.inside}', which is not a node")
        if n.inside == n.name:
            problems.append(f"node {n.name}: it cannot be inside itself")
    inside = {n.name: n.inside for n in graph.nodes}
    for name in names:                                  # no loops
        seen, at = set(), name
        while at in inside and at not in seen:
            seen.add(at)
            at = inside[at]
        if at in seen:
            problems.append(f"node {name}: 'inside' runs in a loop ({' > '.join(sorted(seen))})")
            break
    if graph.nodes and sum(n.inside == "world" for n in graph.nodes) == 0:
        problems.append("no node is inside 'world': the outermost part must be")
    for kind, entries in (("node", graph.nodes), ("property", graph.properties), ("edge", graph.edges)):
        for e in entries:
            label = e.name if kind == "node" else (f"{e.of}: {e.quantity}" if kind == "property" else f"{e.subject} {e.relation} {e.object}")
            unknown = [i for i in e.claims if i not in by_id]
            if unknown:
                problems.append(f"{kind} {label}: there are no claims {', '.join(unknown)}")
            if not e.claims:
                problems.append(f"{kind} {label}: it names no claim")
    for p in graph.properties:
        if p.of not in names:
            problems.append(f"property {p.of}: {p.quantity}: '{p.of}' is not a node")
        if p.derived:
            if not p.reasoning:
                problems.append(f"property {p.of}: {p.quantity}: a derived value needs its reasoning")
            continue
        numbers = [float(p.value)] if isinstance(p.value, (int, float)) else numbers_in(str(p.value))
        stated = [n for i in p.claims if i in by_id and by_id[i].kind == "value"
                  for n in ([float(by_id[i].value)] if isinstance(by_id[i].value, (int, float)) else numbers_in(str(by_id[i].value)))]
        if numbers and not any(abs(n - s) <= 1e-9 * max(abs(s), 1) for n in numbers for s in stated):
            problems.append(f"property {p.of}: {p.quantity} = {p.value}: none of its claims states this number. "
                            "Use the number of the claim, or mark the value as derived and say how")
    for e in graph.edges:
        for end in (e.subject, e.object):
            if end not in names:
                problems.append(f"edge {e.subject} {e.relation} {e.object}: '{end}' is not a node")
        if e.inferred and not e.reasoning:
            problems.append(f"edge {e.subject} {e.relation} {e.object}: an inferred relation needs its reasoning")
        if not e.inferred and not any(i in by_id and by_id[i].kind == "relation" for i in e.claims):
            problems.append(f"edge {e.subject} {e.relation} {e.object}: none of its claims is a relation claim. "
                            "Name the relation claim, or mark the edge as inferred and say how it follows")
    in_graph = {i for entries in (graph.nodes, graph.properties, graph.edges) for e in entries for i in e.claims}
    used = in_graph | {s.claim for s in graph.set_aside}
    missing = [c.id for c in (claims if cover is None else cover) if c.id not in used]
    if missing:
        problems.append("these claims are neither used nor set aside: " + ", ".join(missing))
    both = sorted(in_graph & {s.claim for s in graph.set_aside})
    if both:
        problems.append("these claims are in the graph and also set aside; take them out of set_aside: " + ", ".join(both[:30]))
    for s in graph.set_aside:
        if s.reason in ("same_as", "contradicted_by") and s.other not in in_graph:
            problems.append(f"claim {s.claim} is set aside as {s.reason} {s.other or '(no claim named)'}, but that claim is not "
                            "in the graph. Put one of the two into the graph")
        claim = by_id.get(s.claim)
        if claim and claim.kind == "value" and claim.built and s.reason == "not_geometry" and claim.quantity in G.NEEDED_QUANTITIES:
            problems.append(f"claim {s.claim} ({claim.subject}: {claim.quantity} = {claim.value} {claim.unit}) is a size, count, mass "
                            "or material and was set aside as not geometry. Make it a property")
    return problems


def review(graph, claims, detector, log=None, model=REVIEWER):
    """A second model reads the graph against the claims and says what does not agree."""
    listing = "\n".join(c.line() for c in claims)
    request = (f"A graph of the detector {detector} was built from these claims (id | claim | source):\n{listing}\n\n"
               f"The graph:\n{as_text(to_dict(graph, claims, detector))}\n\n"
               "Check the graph against the claims. List what does not agree: a value on the wrong part, a part "
               "inside the wrong container, two nodes that are the same part, one node that joins two different "
               "parts, a relation that the claims contradict, a part that a claim names and the graph lacks. "
               "Only what the claims show; give the claim id. An empty list if all agrees. "
               'Answer with one JSON object: {"objections": [{"entry": "...", "problem": "..."}]}')
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": request}], Review, log=log,
                                  stage="graph_review", temperature=0)
    except ValueError:
        return []
    return answer.objections


def build(claims, detector, log=None, model=MODEL, with_review=True):
    """The graph of `detector` from its claims. Returns (DetectorGraph, record of the checks)."""
    accepted = [c for c in claims if c.status == "accepted"]
    schema = json.dumps(DetectorGraph.model_json_schema(), separators=(",", ":"))
    messages = [{"role": "user", "content": PROMPT.format(detector=detector, schema=schema,
                                                          claims="\n".join(c.line() for c in accepted))}]
    record = {"rounds": [], "review": [], "removed": [], "unaccounted": []}
    graph, _ = call_llm_json(model, messages, DetectorGraph, log=log, stage="graph_build", temperature=0)
    reviewed = not with_review
    for round_number in range(REPAIRS + 2):
        problems = check(graph, accepted)
        record["rounds"].append(problems)
        objections = []
        if not problems and not reviewed:
            reviewed = True
            objections = review(graph, accepted, detector, log)
            record["review"] = [o.model_dump() for o in objections]
        if (not problems and not objections) or round_number > REPAIRS:
            break
        text = ""
        if problems:
            text += "A program checked your graph and found:\n" + "\n".join(f"- {p}" for p in problems[:40])
        if objections:
            text += ("A reviewer compared your graph with the claims and objects:\n"
                     + "\n".join(f"- {o.entry}: {o.problem}" for o in objections)
                     + "\nChange the graph where the claims bear the reviewer out. Where they do not, leave it.")
        messages += [{"role": "assistant", "content": graph.model_dump_json()},
                     {"role": "user", "content": text + "\n\nSend the complete corrected graph as one JSON object."}]
        try:
            graph, _ = call_llm_json(model, messages, DetectorGraph, log=log, stage="graph_repair", temperature=0)
        except ValueError:
            break
    return _clean(graph, accepted, record)


def _clean(graph, accepted, record):
    """Take out what the checks still reject, so that nothing unsupported stays in the graph."""
    by_id = {c.id: c for c in accepted}
    names = {n.name for n in graph.nodes}

    def supported(p):
        if p.of not in names or not p.claims or any(i not in by_id for i in p.claims):
            return False
        if p.derived:
            return bool(p.reasoning)
        numbers = [float(p.value)] if isinstance(p.value, (int, float)) else numbers_in(str(p.value))
        stated = [n for i in p.claims if by_id[i].kind == "value"
                  for n in ([float(by_id[i].value)] if isinstance(by_id[i].value, (int, float)) else numbers_in(str(by_id[i].value)))]
        return not numbers or any(abs(n - s) <= 1e-9 * max(abs(s), 1) for n in numbers for s in stated)

    keep = [p for p in graph.properties if supported(p)]
    record["removed"] += [f"property {p.of}: {p.quantity} = {p.value}" for p in graph.properties if p not in keep]
    graph.properties = keep
    keep = [e for e in graph.edges if e.subject in names and e.object in names and e.claims and all(i in by_id for i in e.claims)
            and (e.inferred and e.reasoning or any(by_id[i].kind == "relation" for i in e.claims))]
    record["removed"] += [f"edge {e.subject} {e.relation} {e.object}" for e in graph.edges if e not in keep]
    graph.edges = keep
    for n in graph.nodes:
        if n.inside != "world" and n.inside not in names:
            record["removed"].append(f"container of {n.name} ('{n.inside}')")
            n.inside = "world"
        n.claims = [i for i in n.claims if i in by_id]
    used = {i for entries in (graph.nodes, graph.properties, graph.edges) for e in entries for i in e.claims} | \
           {s.claim for s in graph.set_aside}
    record["unaccounted"] = [c.id for c in accepted if c.id not in used]
    return graph, record


class Structure(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    set_aside: list[SetAside] = Field(default_factory=list)


class Values(BaseModel):
    properties: list[NodeProperty]
    set_aside: list[SetAside] = Field(default_factory=list)


def _with_repairs(model, messages, schema, problems_of, log, stage):
    """Ask, check, send the problems back, up to REPAIRS times. Returns (answer, problems of each round)."""
    answer, _ = call_llm_json(model, messages, schema, log=log, stage=stage, temperature=0)
    rounds = []
    for _ in range(REPAIRS + 1):
        problems = problems_of(answer)
        rounds.append(problems)
        if not problems or len(rounds) > REPAIRS:
            break
        messages += [{"role": "assistant", "content": answer.model_dump_json()},
                     {"role": "user", "content": "A program checked your answer and found:\n" + "\n".join(f"- {p}" for p in problems[:40])
                      + "\n\nSend the complete corrected answer as one JSON object."}]
        try:
            answer, _ = call_llm_json(model, messages, schema, log=log, stage=stage + "_repair", temperature=0)
        except ValueError:
            break
    return answer, rounds


def build_in_two(claims, detector, log=None, model=MODEL, batch=70):
    """As build(), in two stages, so that the model never has to hold everything at once: first the parts and
    how they are arranged, from the part, shape, feature and relation claims; then the values, part by part."""
    accepted = [c for c in claims if c.status == "accepted"]
    structure_claims = [c for c in accepted if c.kind != "value"]
    value_claims = [c for c in accepted if c.kind == "value"]
    head = PROMPT[:PROMPT.index("Build the graph:")].format(detector=detector, claims="{claims}")
    rules = PROMPT[PROMPT.index("Rules\n"):PROMPT.index("Answer with one JSON object")]
    nodes_text = PROMPT[PROMPT.index("nodes: one node per physical part."):PROMPT.index("properties: the values of each part")]
    edges_text = PROMPT[PROMPT.index("edges: how the parts are arranged"):PROMPT.index("set_aside: every claim")]
    aside_text = PROMPT[PROMPT.index("set_aside: every claim"):PROMPT.index("Rules\n")]
    values_text = PROMPT[PROMPT.index("properties: the values of each part"):PROMPT.index("edges: how the parts are arranged")]
    request = (head.replace("{claims}", "\n".join(c.line() for c in structure_claims))
               + "First only the parts and how they are arranged; the values follow later.\n\n" + nodes_text + edges_text
               + aside_text + rules + "Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Structure.model_json_schema(), separators=(",", ":")))
    empty = lambda s: DetectorGraph(nodes=s.nodes, properties=[], edges=s.edges, set_aside=s.set_aside)
    structure, rounds = _with_repairs(model, [{"role": "user", "content": request}], Structure,
                                      lambda s: check(empty(s), accepted, structure_claims), log, "graph_structure")
    record = {"rounds": rounds, "review": [], "removed": [], "unaccounted": []}
    graph = empty(structure)
    parts = "\n".join(f"  {n.name}: {n.what} (also called: {', '.join(n.also_called) or '-'}; inside {n.inside})" for n in graph.nodes)
    for start in range(0, len(value_claims), batch):
        some = value_claims[start:start + batch]
        request = (f"You add the values to a graph of the detector {detector}. The parts of the graph:\n{parts}\n\n"
                   "Value claims (id | claim | source). A claim may name its part differently from the graph, or name "
                   "two names for it:\n" + "\n".join(c.line() for c in some) + "\n\n" + values_text
                   + "Use the names of the parts exactly as in the list above for 'of'.\n\n" + aside_text + rules
                   + "Answer with one JSON object that fits this schema and nothing else:\n"
                   + json.dumps(Values.model_json_schema(), separators=(",", ":")))

        def problems_of(v, some=some):
            trial = DetectorGraph(nodes=graph.nodes, properties=graph.properties + v.properties, edges=graph.edges,
                                  set_aside=graph.set_aside + v.set_aside)
            keep = ("property ", "these claims", "claim ")
            return [p for p in check(trial, accepted, some) if p.startswith(keep)]

        try:
            values, more = _with_repairs(model, [{"role": "user", "content": request}], Values, problems_of, log, "graph_values")
        except ValueError:
            record["rounds"].append([f"no usable answer for {len(some)} value claims"])
            continue
        record["rounds"] += more
        graph.properties += values.properties
        graph.set_aside += values.set_aside
    return _clean(graph, accepted, record)


def to_dict(graph, claims, detector, record=None):
    """The graph as plain data, with the quotes of its claims and what each part still lacks."""
    by_id = {c.id: c for c in claims}
    nodes = {n.name: n for n in graph.nodes}

    def sources(ids):
        return [{"claim": i, "quote": by_id[i].quote, "file": by_id[i].file, "page": by_id[i].page, "where": by_id[i].where}
                for i in ids if i in by_id]

    in_graph = {i for entries in (graph.nodes, graph.properties, graph.edges) for e in entries for i in e.claims}
    data = {"detector": detector, "nodes": [], "properties": [], "relations": [],
            "set_aside": [s.model_dump() for s in graph.set_aside if s.claim not in in_graph], "checks": record or {}}
    for p in graph.properties:
        data["properties"].append({**p.model_dump(), "built": True, "sources": sources(p.claims),
                                   "quote": " ".join(by_id[i].quote for i in p.claims if i in by_id),
                                   "found_by": "derived" if p.derived else "claims"})
    for n in graph.nodes:                               # the container is an edge too
        if n.inside != "world":
            data["relations"].append({"subject": n.inside, "relation": "contains", "object": n.name, "count": None,
                                      "claims": n.claims, "inferred": False, "reasoning": "", "sources": sources(n.claims),
                                      "quote": "", "found_by": "inside", "nesting": True})
    for e in graph.edges:
        if (e.subject, "contains", e.object) in {(r["subject"], r["relation"], r["object"]) for r in data["relations"]}:
            continue
        data["relations"].append({**e.model_dump(), "sources": sources(e.claims),
                                  "quote": " ".join(by_id[i].quote for i in e.claims if i in by_id),
                                  "found_by": "inferred" if e.inferred else "claims"})
    for n in graph.nodes:
        entry = {**n.model_dump(), "about": [detector], "sources": sources(n.claims)}
        have = {p.quantity for p in graph.properties if p.of == n.name}
        missing = []
        if n.form != "filling":
            if n.shape in ("not_stated", "other"):
                missing.append("shape")
            for options in G.NEEDED.get(n.shape, []):
                if not have & set(options):
                    missing.append(options[0])
            if n.shape in ("not_stated", "other") and not have & {"diameter", "radius", "height", "length", "width", "thickness"}:
                missing.append("any size")
            if "material" not in have:
                missing.append("material")
        placed = n.inside != "world" or any(e.subject == n.name or e.object == n.name for e in graph.edges)
        if not placed and sum(m.inside == "world" for m in graph.nodes) > 1:
            missing.append("where it is")
        entry["unknown"] = missing
        data["nodes"].append(entry)
    return data


def as_text(data):
    """The graph as an indented tree by 'inside', with the other relations below."""
    nodes = {n["name"]: n for n in data["nodes"]}
    lines = [f"Detector graph of {data['detector']}: {len(nodes)} parts, {len(data['properties'])} properties, "
             f"{len(data['relations'])} relations", ""]

    def describe(n):
        values = [f"{p['quantity']}{'' if p['which'] in ('', 'not_stated') else ' (' + p['which'] + ')'} "
                  f"{'' if p['wording'] in ('', 'exact') else p['wording'].replace('_', ' ') + ' '}{p['value']} {p['unit']}".strip()
                  + (" [derived]" if p["derived"] else "") for p in data["properties"] if p["of"] == n["name"]]
        text = f"{n['name']} [{n['form']}{'' if n['shape'] == 'not_stated' else ', ' + n['shape']}]"
        if values:
            text += ": " + "; ".join(values)
        if n["features"]:
            text += "  {" + ", ".join(n["features"]) + "}"
        return text + (f"   UNKNOWN: {', '.join(n['unknown'])}" if n["unknown"] else "")

    def walk(name, depth):
        for n in data["nodes"]:
            if n["inside"] == name:
                lines.append("  " * depth + ("└─ " if depth else "") + describe(n))
                walk(n["name"], depth + 1)

    walk("world", 0)
    others = [r for r in data["relations"] if not r.get("nesting")]
    if others:
        lines += ["", "Other relations:"]
        lines += [f"  {r['subject']} {r['relation'].replace('_', ' ')} {r['object']}{' x' + str(r['count']) if r.get('count') else ''}"
                  + (f"   [inferred: {r['reasoning']}]" if r.get("inferred") else "") for r in others]
    if data.get("set_aside"):
        lines += ["", f"Claims set aside: {len(data['set_aside'])}"]
    return "\n".join(lines)


def graph_step(folder, detector, log=None):
    """Build the graph from claims.jsonl in `folder`, in two stages (see experiments/notes/claims_graph.md).
    Writes detector_graph.json and detector_graph.txt."""
    folder = Path(folder)
    claims = C.load(folder)
    graph, record = build_in_two(claims, detector, log)
    data = to_dict(graph, [c for c in claims if c.status == "accepted"], detector, record)
    (folder / "detector_graph.json").write_text(json.dumps(data, indent=1))
    (folder / "detector_graph.txt").write_text(as_text(data) + "\n")
    return data


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    print(as_text(graph_step(args[0], name)))
