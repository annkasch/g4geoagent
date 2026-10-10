"""Knowledge graph of a detector: parts as nodes, relations as edges, every entry with its source.

    python -m g4geoagent.agent.graph <output folder> <paper.txt> [<paper.pdf>] [--name "LEGEND-200"]

Two readers extract parts, properties and relations from the text with the template of
graph_schemas.py. A program checks every quote against the document and merges the two
readings: an entry both readers have is "agreed", an entry of one reader is kept and marked.
Figures of the PDF are read by one vision model and marked "from a figure".
What a part still lacks to be built is listed as unknown: that is what research has to find.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from g4geoagent.agent.compare import _squash, locate, numbers_in, sentences
from g4geoagent.agent.graph_schemas import Extraction
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.readers import READERS

NESTING = ("contains", "encloses", "surrounds")           # edges that say: the object is within the subject
PLACING = (*NESTING, "at_bottom_of", "at_top_of", "centred_in", "mounted_on", "attached_to", "outside", "consists_of")
NEEDED = {"cylinder": [("diameter", "radius"), ("height", "length")], "tube": [("diameter", "radius"), ("height", "length")],
          "box": [("length",), ("width",), ("height", "thickness")], "plate": [("length", "diameter"), ("thickness",)],
          "sphere": [("diameter", "radius")]}

PROMPT = """You read a document about a particle detector and write down how the detector is built, so that a
geometry model can be made from it. Extract three kinds of records.

parts: every physical part of the detector that the document names: vessels, shields, liquids and gases that fill
them, sensitive detectors, sensors, supports, electronics. One record per part, in the singular.

properties: every value that describes a part: sizes, masses, volumes, counts, materials. A value belongs to the
thing it measures: "a cryostat with 64 m3 of liquid argon" gives the volume of the liquid argon, not of the cryostat.
Keep the wording: "about 6 t" is wording 'about', "up to 90%" is 'up_to', "more than 60%" is 'at_least'.
Say 'each' or 'total' where the document makes it clear. Values that are not geometry (voltages, temperatures,
energies, rates, dates) get built = false.

relations: every statement about how two parts are arranged: what contains what, what surrounds or encloses what,
what is concentric, at the bottom, at the top, at the centre, mounted on, attached to, outside of, and what a part
consists of. "A is inside B" is written as: B contains A. One record per statement.

Rules
- Use only what the document says. Do not add knowledge of your own.
- Every record needs a quote: the exact words of the document, copied character by character, from one sentence.
  A quote for a property must contain the value.
- Use the same name for a part in all records.
- 'about' names the detector or experiment the statement describes. A document may mention other experiments.
{procedure}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""

FIGURE_PROMPT = """This figure is from a paper about the detector {detector}. Its caption: "{caption}".

Write down what the figure shows about how the detector is built, as the same three kinds of records as for text:
parts (use the labels written in the figure as names where there are labels), properties (only values that are
written in the figure), and relations between parts that one can see: what contains what, what surrounds what,
what is at the top, at the bottom or at the centre, what is mounted on or attached to what, what consists of
several pieces. Under 'features' of a part, say what its shape shows: 'domed ends', 'neck at the top',
'double-walled', 'hollow', 'many panels', 'stack of units'. For 'quote' give the label in the figure, or a few words
describing where in the figure it is seen. Say only what you can see.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def norm(name):
    """A part name reduced to what identifies it: lower case, underscores, no plural s."""
    text = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return re.sub(r"(?<=[a-z]{3})s$", "", text)


def read_text(documents, reader, log=None):
    """One reader's Extraction of the text documents ({file name: text})."""
    model, procedure = READERS[reader]
    text = "\n\n".join(f"===== Document: {name} =====\n{body}" for name, body in documents.items())
    schema = json.dumps(Extraction.model_json_schema(), separators=(",", ":"))
    messages = [{"role": "system", "content": PROMPT.format(procedure="- " + procedure, schema=schema)},
                {"role": "user", "content": text}]
    answer, _ = call_llm_json(model, messages, Extraction, log=log, stage=f"graph_reader_{reader}", temperature=0)
    return answer


def read_figure(figure, folder, detector, log=None, model="lbl/gemma-4"):
    """What one figure shows, as an Extraction. None if the model gives no usable answer."""
    from g4geoagent.reviewer.look import _image
    schema = json.dumps(Extraction.model_json_schema(), separators=(",", ":"))
    request = FIGURE_PROMPT.format(detector=detector, caption=figure["caption"], schema=schema)
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": [{"type": "text", "text": request},
                                                                       _image(Path(folder) / figure["file"])]}],
                                  Extraction, log=log, stage="graph_figure", temperature=0)
    except ValueError:
        return None
    return answer


def check(extraction, documents):
    """Drop records whose quote is not in the documents, or whose value is not in the quote.
    Returns (kept Extraction, list of dropped records with the reason)."""
    whole = _squash(" ".join(documents.values()))
    kept, dropped = {"parts": [], "properties": [], "relations": []}, []
    for kind in kept:
        for record in getattr(extraction, kind):
            quote = _squash(record.quote)
            problem = "" if quote and quote in whole else "quote is not in the document"
            if not problem and kind == "properties" and isinstance(record.value, (int, float)):
                words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
                stated = numbers_in(record.quote) + [float(words[w]) for w in re.findall(r"[a-z]+", record.quote.lower()) if w in words]
                if float(record.value) not in stated:
                    problem = "quote does not contain the value"
            if problem:
                dropped.append({"kind": kind, "problem": problem, **record.model_dump()})
            else:
                kept[kind].append(record)
    return Extraction(**kept), dropped


def _sentence(quote, documents):
    for name, text in documents.items():
        parts = sentences(text)
        found = sorted(locate(quote, text))
        if found:
            page = re.findall(r"\[page (\d+)\]", " ".join(parts[:found[0] + 1]))
            return {"file": name, "page": int(page[-1]) if page else None, "sentence": " ".join(parts[i] for i in found)[:400]}
    return {"file": "", "page": None, "sentence": ""}


def merge(readings, documents, detector):
    """One graph from several checked readings ({reader name: Extraction}; a name starting with 'figure' marks
    a reading of a figure). Returns a dict with nodes, properties, relations."""
    # names that mean the same part: joined when two parts share a name or another name
    group = {}

    def find(key):
        while group.setdefault(key, key) != key:
            key = group[key]
        return key

    for extraction in readings.values():
        for part in extraction.parts:
            keys = [norm(part.name), *(norm(a) for a in part.also_called if norm(a))]
            for other in keys[1:]:
                group[find(other)] = find(keys[0])
    nodes = {}

    def node(name):
        key = find(norm(name))
        return nodes.setdefault(key, {"name": key, "also_called": set(), "what": "", "shape": "not_stated", "features": set(),
                                      "detail": "", "about": set(), "readers": set(), "quotes": []})

    def where(reader, quote):
        if reader.startswith("figure"):
            return {"file": reader.split(":", 1)[1], "page": None, "sentence": "", "status": "from a figure"}
        return {**_sentence(quote, documents), "status": "stated"}

    for reader, extraction in readings.items():
        for part in extraction.parts:
            n = node(part.name)
            n["also_called"] |= {part.name, *part.also_called} - {n["name"]}
            n["what"] = n["what"] or part.what
            n["shape"] = part.shape if n["shape"] == "not_stated" else n["shape"]
            n["features"] |= {f.lower() for f in part.features}
            n["detail"] = n["detail"] or part.detail
            n["about"].add(part.about)
            n["readers"].add(reader)
            n["quotes"].append({"reader": reader, "quote": part.quote, **where(reader, part.quote)})
    properties, relations = {}, {}
    for reader, extraction in readings.items():
        for p in extraction.properties:
            value = round(float(p.value), 6) if isinstance(p.value, (int, float)) else re.sub(r"\W+", " ", str(p.value).lower()).strip()
            key = (node(p.of)["name"], p.quantity if p.quantity != "other" else p.quantity_other.lower(), value)
            entry = properties.setdefault(key, {"of": key[0], "quantity": key[1], "which": p.which, "value": p.value, "unit": p.unit,
                                                "wording": p.wording, "built": p.built, "about": p.about, "readers": set(),
                                                "quote": p.quote, **where(reader, p.quote)})
            entry["readers"].add(reader)
            node(p.of)["readers"].add(reader)
        for r in extraction.relations:
            key = (node(r.subject)["name"], r.relation, node(r.object)["name"])
            if key[0] == key[2]:
                continue
            entry = relations.setdefault(key, {"subject": key[0], "relation": r.relation, "object": key[2], "count": r.count,
                                               "about": r.about, "readers": set(), "quote": r.quote, **where(reader, r.quote)})
            entry["readers"].add(reader)
            entry["count"] = entry["count"] or r.count
    text_readers = {r for r in readings if not r.startswith("figure")}

    def agreement(readers):
        both = text_readers and text_readers <= readers
        return "both readers" if both else ", ".join(sorted("figure" if r.startswith("figure") else "reader " + r for r in readers))

    graph = {"detector": detector, "nodes": [], "properties": [], "relations": []}
    for n in nodes.values():
        graph["nodes"].append({**n, "also_called": sorted(n["also_called"]), "features": sorted(n["features"]),
                               "about": sorted(n["about"]), "found_by": agreement(n["readers"]), "readers": sorted(n["readers"])})
    for entry in properties.values():
        graph["properties"].append({**entry, "found_by": agreement(entry["readers"]), "readers": sorted(entry["readers"])})
    for entry in relations.values():
        graph["relations"].append({**entry, "found_by": agreement(entry["readers"]), "readers": sorted(entry["readers"])})
    for n in graph["nodes"]:
        n["unknown"] = unknown(n, graph)
    return graph


def unknown(node, graph):
    """What the graph does not say about a part and a build would need."""
    have = {p["quantity"] for p in graph["properties"] if p["of"] == node["name"] and p["built"]}
    missing = []
    if node["shape"] in ("not_stated", "other"):
        missing.append("shape")
    for options in NEEDED.get(node["shape"], []):
        if not have & set(options):
            missing.append(options[0])
    if node["shape"] in ("not_stated", "other") and not have & {"diameter", "radius", "height", "length", "width", "thickness"}:
        missing.append("any size")
    if "material" not in have:
        missing.append("material")
    placed = [r for r in graph["relations"] if (r["object"] == node["name"] and r["relation"] in NESTING)
              or (r["subject"] == node["name"] and r["relation"] in PLACING and r["relation"] not in NESTING)]
    if not placed:
        missing.append("where it is")
    return missing


def as_text(graph):
    """The graph as an indented tree with the other relations and the unknowns below it."""
    nodes = {n["name"]: n for n in graph["nodes"]}
    children, has_parent = {}, set()
    for r in graph["relations"]:
        if r["relation"] in NESTING and r["object"] not in has_parent:
            children.setdefault(r["subject"], []).append((r["object"], r))
            has_parent.add(r["object"])
    lines = [f"Knowledge graph of {graph['detector']}: {len(graph['nodes'])} parts, {len(graph['properties'])} properties, "
             f"{len(graph['relations'])} relations", ""]

    def describe(name):
        n = nodes[name]
        values = [f"{p['quantity']}{'' if p['which'] == 'not_stated' else ' (' + p['which'] + ')'} "
                  f"{'' if p['wording'] == 'exact' else p['wording'].replace('_', ' ') + ' '}{p['value']} {p['unit']}".strip()
                  for p in graph["properties"] if p["of"] == name and p["built"]]
        text = name + (f" [{n['shape']}]" if n["shape"] != "not_stated" else "")
        if values:
            text += ": " + "; ".join(values)
        if n["features"]:
            text += "  {" + ", ".join(n["features"]) + "}"
        return text + (f"   UNKNOWN: {', '.join(n['unknown'])}" if n["unknown"] else "")

    def walk(name, depth, seen):
        for child, relation in children.get(name, []):
            if child in seen:
                continue
            count = f" x{relation['count']}" if relation.get("count") else ""
            lines.append("  " * depth + f"└─ {relation['relation']}{count}: {describe(child)}   ({relation['found_by']})")
            walk(child, depth + 1, seen | {child})

    for name in nodes:
        if name not in has_parent:
            lines.append(describe(name))
            walk(name, 1, {name})
    others = [r for r in graph["relations"] if r["relation"] not in NESTING]
    if others:
        lines += ["", "Other relations:"]
        lines += [f"  {r['subject']} {r['relation'].replace('_', ' ')} {r['object']}"
                  f"{' x' + str(r['count']) if r.get('count') else ''}   ({r['found_by']})" for r in others]
    return "\n".join(lines)


def build_graph(folder, text_files, pdf=None, detector="detector", log=None):
    """Read, check and merge. Writes graph.json, graph.txt and dropped.json into `folder`."""
    from g4geoagent.reviewer import look
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    documents = {Path(f).name: Path(f).read_text() for f in text_files}
    with ThreadPoolExecutor(2) as pool:
        raw = dict(zip("AB", pool.map(lambda r: read_text(documents, r, log), "AB")))
    readings, dropped = {}, []
    for reader, extraction in raw.items():
        readings[reader], out = check(extraction, documents)
        dropped += [{"reader": reader, **d} for d in out]
    if pdf:
        figures = look.extract_figures(pdf, folder / "figures")
        for figure in look.construction_figures(figures, folder / "figures", detector, log, most=len(figures)):
            seen = read_figure(figure, folder / "figures", detector, log)
            if seen:
                readings[f"figure:{figure['file']}"] = seen
    graph = merge(readings, documents, detector)
    (folder / "graph.json").write_text(json.dumps(graph, indent=1, default=sorted))
    (folder / "graph.txt").write_text(as_text(graph) + "\n")
    (folder / "dropped.json").write_text(json.dumps(dropped, indent=1))
    return graph, dropped


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    files = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] != "--name"]
    graph, dropped = build_graph(args[0], [f for f in files if not f.endswith(".pdf")],
                                 next((f for f in files if f.endswith(".pdf")), None), name)
    print(as_text(graph))
    print(f"\n{len(dropped)} records dropped by the quote check")
