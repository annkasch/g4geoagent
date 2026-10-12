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

from pydantic import BaseModel, Field

from g4geoagent.agent.compare import _squash, locate, numbers_in, sentences
from g4geoagent.agent.graph_schemas import RELATIONS, Extraction, Property, Relation
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.readers import READERS

NESTING = ("contains", "encloses", "surrounds")           # edges that say: the object is within the subject
PLACING = (*NESTING, "at_bottom_of", "at_top_of", "centred_in", "mounted_on", "attached_to", "outside", "consists_of", "next_to")
NEEDED_QUANTITIES = {"diameter", "radius", "height", "length", "width", "thickness", "mass", "volume", "count", "material"}
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

PROMPT_2 = """You read a document about a particle detector and write down how the detector is built, so that a
geometry model can be made from it. Extract three kinds of records.

parts: every physical part of the detector that the document names: vessels, shields, liquids and gases that fill
them, sensitive detectors, sensors, supports, electronics. One record per part, in the singular. Give the shape
if the document says or clearly implies it (a tank with a diameter and a height is a cylinder).

properties: every value that describes a part.
- Sizes, masses, volumes. A value belongs to the thing it measures: "a cryostat with 64 m3 of liquid argon" gives
  the volume of the liquid argon, not of the cryostat.
- Materials. What a part is made of is a property with quantity 'material' and the material as text value:
  "a stainless steel cryostat" gives cryostat, material, "stainless steel". What fills a vessel is a part of its own.
- Counts. How many there are of a part is a property with quantity 'count': "66 PMTs", "arranged in 12 strings",
  "a 7 x 5 array of modules" (value "7 x 5"), "three fibres per cube" (count 3, which 'each'). A count written
  as a word ("seven strings") is given as a number.
- Keep the wording: "about 6 t" is 'about', "up to 90%" is 'up_to', "more than 60%" is 'at_least'.
- Say 'each' for one item of a repeated part and 'total' for all together, where the document makes it clear.
- Values that are not geometry (voltages, temperatures, energies, rates, dates, resolutions) get built = false.

relations: every statement about how two parts are arranged. Use:
- contains: "A is inside B", "B is filled with A", "B houses A" are all written as B contains A.
- surrounds, encloses: A is around B.
- consists_of: A is made up of several B ("an array of modules", "6 planes"); give the count if stated.
- mounted_on, attached_to: A is fixed to B. A sensor that reads out a part is attached_to that part.
- next_to: A is beside, upstream or downstream of B. "A sandwiched between two B" is A next_to B.
- at_bottom_of, at_top_of, centred_in, concentric_with, outside.
One record per statement. Give every part a relation that says where it is, if the document says so anywhere.

Rules
- Use only what the document says. Do not add knowledge of your own.
- Every record needs a quote: a short run of exact words of the document, at most about 20 words, from one
  sentence, copied character by character, without reference marks such as [8]. A quote for a number must
  contain the number as it is written.
- Use the same name for a part in all records.
- 'about' names the detector or experiment the statement describes. Statements about other experiments, earlier
  versions or prototypes are still recorded, with their own name under 'about'.
{procedure}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""

PROMPT_3 = """You read a document about a particle detector and write down how the detector is built, so that a
geometry model can be made from it. Extract three kinds of records.

parts: every physical part of the detector that the document names: vessels, shields, liquids and gases that fill
them, sensitive detectors, sensors, supports, electronics. One record per part, in the singular. Give the shape
if the document says or clearly implies it (a tank with a diameter and a height is a cylinder).
- The detector as a whole is a part too, when the document says what it is made up of ("the detector suite
  consists of A, B and C"): then the whole consists_of each of them.
- A vessel and what fills it are two parts: "a tank with 590 m3 of water" gives the tank, the water, and the
  relation: tank contains water.

properties: every value that describes a part.
- Sizes, masses, volumes. A value belongs to the thing it measures: "a cryostat with 64 m3 of liquid argon" gives
  the volume of the liquid argon, not of the cryostat. A value in brackets belongs to the thing named just
  before the brackets.
- Values in tables and in figure captions count like values in the text.
- Materials. What a part is made of is a property with quantity 'material' and the material as text value:
  "a stainless steel cryostat" gives cryostat, material, "stainless steel". What fills a vessel is a part of its own.
- Counts. How many there are of a part is a property with quantity 'count': "66 PMTs", "arranged in 12 strings",
  "a 7 x 5 array of modules" (value "7 x 5"), "three fibres per cube" (count 3, which 'each'). A count written
  as a word ("seven strings") is given as a number.
- Keep the wording: "about 6 t" is 'about', "up to 90%" is 'up_to', "more than 60%" is 'at_least'.
- 'each' is only for one item of a part that exists many times (one PMT of 66), 'total' for all of them
  together (the mass of the whole array). For a part that exists once, leave it 'not_stated'.
- Values that are not geometry (voltages, temperatures, energies, rates, dates, resolutions) get built = false.

relations: every statement about how two parts are arranged. Use:
- contains: "A is inside B", "B is filled with A", "B houses A" are all written as B contains A.
- surrounds, encloses: A is around B.
- consists_of: A is made up of several B ("an array of modules", "6 planes"); give the count if stated.
- mounted_on, attached_to: A is fixed to B. A sensor that reads out a part is attached_to that part.
- next_to: A is beside, upstream or downstream of B. "A sandwiched between two B" is A next_to B.
- at_bottom_of, at_top_of, centred_in, concentric_with, outside.
One record per statement. Give every part a relation that says where it is, if the document says so anywhere.

Rules
- Use only what the document says. Do not add knowledge of your own.
- Every record needs a quote: a short run of exact words of the document, at most about 20 words, from one
  sentence, copied character by character, without reference marks such as [8]. A quote for a number must
  contain the number as it is written.
- Use the same name for a part in all records.
- 'about' names the detector or experiment the statement describes. Statements about other experiments, earlier
  versions or prototypes are still recorded, with their own name under 'about'.
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


def read_text(documents, reader, log=None, prompt=None, seed=None):
    """One reader's Extraction of the text documents ({file name: text})."""
    model, procedure = READERS[reader]
    prompt = prompt or PROMPT
    text = "\n\n".join(f"===== Document: {name} =====\n{body}" for name, body in documents.items())
    schema = json.dumps(Extraction.model_json_schema(), separators=(",", ":"))
    messages = [{"role": "system", "content": prompt.format(procedure="- " + procedure, schema=schema)},
                {"role": "user", "content": text}]
    options = {} if seed is None else {"seed": seed}
    answer, _ = call_llm_json(model, messages, Extraction, log=log, stage=f"graph_reader_{reader}", temperature=0, **options)
    return answer


def union(*extractions):
    """The records of several readings by the same reader, each one once."""
    seen, out = set(), {"parts": [], "properties": [], "relations": []}
    for extraction in extractions:
        for kind in out:
            for record in getattr(extraction, kind):
                key = (kind, _squash(record.quote), str(getattr(record, "value", getattr(record, "relation", ""))),
                       norm(getattr(record, "name", getattr(record, "of", getattr(record, "subject", "")))))
                if key not in seen:
                    seen.add(key)
                    out[kind].append(record)
    return Extraction(**out)


def read_figure(figure, folder, detector, log=None, model="lbl/gemma-4", prompt=None):
    """What one figure shows, as an Extraction. None if the model gives no usable answer."""
    from g4geoagent.reviewer.look import _image
    schema = json.dumps(Extraction.model_json_schema(), separators=(",", ":"))
    request = (prompt or FIGURE_PROMPT).format(detector=detector, caption=figure["caption"], schema=schema)
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": [{"type": "text", "text": request},
                                                                       _image(Path(folder) / figure["file"])]}],
                                  Extraction, log=log, stage="graph_figure", temperature=0)
    except ValueError:
        return None
    return answer


REFERENCE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\(\s*(?:see\s+)?(?:Fig|Sec|Tab)[^)]*\)")


def _repair(quote, whole, must_hold=None):
    """The longest run of at least 5 words of `quote` that is in the document (given squashed), and that
    holds the value if there is one. Readers often copy a sentence and leave out a reference mark."""
    words = quote.split()
    for length in range(len(words) - 1, 4, -1):
        for start in range(len(words) - length + 1):
            part = " ".join(words[start:start + length])
            if _squash(part) in whole and (must_hold is None or must_hold in numbers_in(part)):
                return part
    return None


def check(extraction, documents, tolerant=False):
    """Drop records whose quote is not in the documents, or whose value is not in the quote.
    With `tolerant`, reference marks such as [8] are ignored, and a quote that fails is cut down to
    its longest part that is in the document. Returns (kept Extraction, dropped records with the reason)."""
    text = " ".join(documents.values())
    whole = _squash(REFERENCE.sub(" ", text) if tolerant else text)
    kept, dropped = {"parts": [], "properties": [], "relations": []}, []
    for kind in kept:
        for record in getattr(extraction, kind):
            if tolerant:
                record.quote = REFERENCE.sub(" ", record.quote)
            quote = _squash(record.quote)
            problem = "" if quote and quote in whole else "quote is not in the document"
            if problem and tolerant:
                number = float(record.value) if kind == "properties" and isinstance(record.value, (int, float)) else None
                shorter = _repair(record.quote, whole, number)
                if shorter:
                    record.quote, problem = shorter, ""
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


FAMILY = {"contains": "within", "encloses": "within", "surrounds": "within", "consists_of": "within",
          "mounted_on": "joined", "attached_to": "joined", "next_to": "beside", "concentric_with": "concentric"}
SPECIFIC = ["surrounds", "encloses", "consists_of", "contains", "mounted_on", "attached_to"]     # the more telling word wins


def merge(readings, documents, detector, by_family=False, same=(), figures_extend_only=False, tidy_values=False):
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
    for names in same:                              # names that a later step found to mean the same part
        keys = [norm(n) for n in names]
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

    seen_only = []
    if figures_extend_only:
        # a figure may add to parts that the text names. A part that only a figure shows is kept apart,
        # as something to look for, and so are relations and properties that involve such a part.
        in_text = {find(norm(x)) for r, e in readings.items() if not r.startswith("figure")
                   for p in e.parts for x in (p.name, *p.also_called) if norm(x)}
        trimmed = {}
        for reader, extraction in readings.items():
            if not reader.startswith("figure"):
                trimmed[reader] = extraction
                continue
            known = lambda name: find(norm(name)) in in_text
            seen_only += [{"name": norm(p.name), "what": p.what, "features": p.features, "figure": reader.split(":", 1)[1]}
                          for p in extraction.parts if not known(p.name)]
            trimmed[reader] = Extraction(parts=[p for p in extraction.parts if known(p.name)],
                                         properties=[p for p in extraction.properties if known(p.of)],
                                         relations=[r for r in extraction.relations if known(r.subject) and known(r.object)])
        readings = trimmed
    for reader, extraction in readings.items():
        for part in extraction.parts:
            n = node(part.name)
            n["also_called"] |= {part.name, *part.also_called} - {n["name"]}
            n["what"] = n["what"] or part.what
            n["shape"] = part.shape if n["shape"] == "not_stated" else n["shape"]
            n["features"] |= {re.sub(r"[\u2010-\u2015\u2212]", "-", f.lower()).strip() for f in part.features}
            n["detail"] = n["detail"] or part.detail
            n["about"].add(part.about)
            n["readers"].add(reader)
            n["quotes"].append({"reader": reader, "quote": part.quote, **where(reader, part.quote)})
    properties, relations = {}, {}
    for reader, extraction in readings.items():
        for p in extraction.properties:
            if tidy_values and isinstance(p.value, str):
                # "about 6 t" written as text is the number 6 with the unit t and the wording "about"
                found = re.fullmatch(r"\s*(about|approximately|around|~|∼|up to|more than|at least)?\s*([-+]?\d+(?:\.\d+)?)\s*([A-Za-zμµ%³0-9/]*)\s*", p.value)
                if found and p.quantity != "material":
                    word = {"up to": "up_to", "more than": "at_least", "at least": "at_least"}.get(found.group(1) or "", "about" if found.group(1) else p.wording)
                    p = p.model_copy(update={"value": float(found.group(2)), "unit": p.unit or found.group(3), "wording": word})
            value = round(float(p.value), 6) if isinstance(p.value, (int, float)) else re.sub(r"\W+", " ", str(p.value).lower()).strip()
            key = (node(p.of)["name"], p.quantity if p.quantity != "other" else p.quantity_other.lower(), value)
            if by_family and isinstance(p.value, (int, float)):
                key = (key[0], value, "" if tidy_values else _squash(p.unit))      # the same number on the same part is the same statement
            entry = properties.setdefault(key, {"of": node(p.of)["name"], "quantity": p.quantity if p.quantity != "other" else p.quantity_other.lower(), "which": p.which, "value": p.value, "unit": p.unit,
                                                "wording": p.wording, "built": p.built, "about": p.about, "readers": set(),
                                                "quote": p.quote, **where(reader, p.quote)})
            entry["readers"].add(reader)
            node(p.of)["readers"].add(reader)
        for r in extraction.relations:
            key = (node(r.subject)["name"], r.relation, node(r.object)["name"])
            if key[0] == key[2]:
                continue
            if by_family:
                family = FAMILY.get(r.relation, r.relation)
                ends = tuple(sorted((key[0], key[2]))) if family in ("joined", "beside", "concentric") else (key[0], key[2])
                key = (family, *ends)
                if key in relations:
                    known = relations[key]
                    rank = lambda word: SPECIFIC.index(word) if word in SPECIFIC else len(SPECIFIC)
                    if rank(r.relation) < rank(known["relation"]):
                        known.update(subject=node(r.subject)["name"], relation=r.relation, object=node(r.object)["name"])
            entry = relations.setdefault(key, {"subject": node(r.subject)["name"], "relation": r.relation, "object": node(r.object)["name"], "count": r.count,
                                               "about": r.about, "readers": set(), "quote": r.quote, **where(reader, r.quote)})
            entry["readers"].add(reader)
            entry["count"] = entry["count"] or r.count
    text_readers = {r for r in readings if not r.startswith("figure")}

    def agreement(readers):
        both = text_readers and text_readers <= readers
        return "both readers" if both else ", ".join(sorted("figure" if r.startswith("figure") else "reader " + r for r in readers))

    graph = {"detector": detector, "nodes": [], "properties": [], "relations": [], "seen_only_in_figures": seen_only}
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


class Verdict(BaseModel):
    item: int
    verdict: str = Field(description="'confirmed', 'corrected', 'wrong' or 'not_construction'")
    relation: str = Field(default="", description="For 'corrected': the relation that the sentence does state")
    swap: bool = Field(default=False, description="For 'corrected': true if subject and object have to change places")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


def cross_check(readings, documents, detector, log=None, known=None, correct=False, votes=1):
    """Every property and relation that only one reader has goes to the other reader, with the sentence it was
    taken from. Confirmed records count for both readers. Records judged wrong are taken out and returned as
    disputed. A property judged not to be construction is kept as not built; such a relation is taken out.
    With `correct`, the checker may put right the kind of a relation ("the huts are on top of the tank", not in it)
    instead of rejecting it.
    With `votes` above 1 the checker is asked that many times; an entry is taken out only if every answer
    rejects it, and it counts as confirmed if any answer confirms it.
    `known` is a dict of earlier verdicts ({signature: verdict}) and is filled in, so that it can be kept on disk.
    Returns (readings, disputed)."""
    known = {} if known is None else known
    graph = merge({r: e for r, e in readings.items() if not r.startswith("figure")}, documents, detector, by_family=True)
    disputed = []
    for reader, other in (("A", "B"), ("B", "A")):
        single = [("property", p) for p in graph["properties"] if p["readers"] == [reader]] + \
                 [("relation", r) for r in graph["relations"] if r["readers"] == [reader]]

        def signature(kind, entry):
            return f"{other}|{kind}|{entry.get('of', entry.get('subject'))}|{entry.get('quantity', entry.get('relation'))}|" \
                   f"{entry.get('value', entry.get('object'))}|{_squash(entry['quote'])[:80]}"

        for vote in range(votes):
            tag = "" if vote == 0 else f"#{vote}"
            ask = [(kind, entry) for kind, entry in single if signature(kind, entry) + tag not in known]
            for start in range(0, len(ask), 20):
                batch = ask[start:start + 20]
                items = []
                for i, (kind, e) in enumerate(batch):
                    stated = (f"{e['of']}: {e['quantity']} = {e['value']} {e['unit']}" if kind == "property"
                              else f"{e['subject']} {e['relation'].replace('_', ' ')} {e['object']}")
                    items.append(f"{i}. {stated}\n   sentence: \"{(e.get('sentence') or e['quote'])[:500]}\"")
                request = (f"Another reader extracted these statements about how the detector {detector} is built. Check "
                           "each one against the sentence it was taken from.\n- 'confirmed': the sentence says this.\n"
                           "- 'wrong': the sentence does not say this, or says it about another part or another quantity.\n"
                           "- 'not_construction': the sentence says it, but it is not about how the detector is built "
                           "(a physics result, a performance figure, an operating value).\n"
                           + ("- 'corrected': for a relation between two parts that the sentence does relate, but in another "
                              "way. Give the right relation, one of: " + ", ".join(RELATIONS) + "; and swap = true if subject "
                              "and object have to change places. Prefer this over 'wrong' when the two parts do belong "
                              "together.\n" if correct else "")
                           + "\nItems:\n" + "\n".join(items)
                           + '\n\nAnswer with one JSON object: {"verdicts": [{"item": 0, "verdict": "confirmed"}, ...]}')
                try:
                    answer, _ = call_llm_json(READERS[other][0], [{"role": "user", "content": request}], Verdicts, log=log,
                                              stage=f"graph_cross_check_{other}", temperature=0, **({"seed": vote} if vote else {}))
                    given = {v.item: (v.verdict if v.verdict != "corrected" else f"corrected:{v.relation}:{int(v.swap)}")
                             for v in answer.verdicts}
                except ValueError:
                    given = {}
                for i, (kind, e) in enumerate(batch):
                    known[signature(kind, e) + tag] = given.get(i, "confirmed")
        for kind, e in single:
            answers = [known.get(signature(kind, e) + ("" if v == 0 else f"#{v}"), "confirmed") for v in range(votes)]
            kinds = [a.split(":")[0] for a in answers]
            verdict = (next((a for a in answers if a == "confirmed"), None) or next((a for a in answers if a.startswith("corrected:")), None)
                       or ("not_construction" if "not_construction" in kinds else "wrong"))
            records = readings[reader].properties if kind == "property" else readings[reader].relations
            match = [r for r in records if _squash(r.quote) == _squash(e["quote"]) and
                     (norm(r.of) if kind == "property" else norm(r.subject)) in
                     {norm(e.get("of", e.get("subject"))), *[norm(a) for n in graph["nodes"] if n["name"] == e.get("of", e.get("subject")) for a in n["also_called"]]}]
            if verdict.startswith("corrected:") and kind == "relation" and verdict.split(":")[1] in RELATIONS:
                _, relation, swap = verdict.split(":")
                for r in match:
                    r.relation = relation
                    if swap == "1":
                        r.subject, r.object = r.object, r.subject
                verdict = "confirmed"
            if verdict == "confirmed":
                target = readings[other].properties if kind == "property" else readings[other].relations
                target += match[:1]
            elif verdict == "not_construction" and kind == "property":
                for r in match:
                    r.built = False
            else:
                disputed.append({"kind": kind, "reader": reader, "verdict": verdict, **{k: v for k, v in e.items() if k != "readers"}})
                for r in match:
                    records.remove(r)
    return readings, disputed


class Missed(BaseModel):
    item: int
    construction: bool = Field(description="true if the number states how the detector is built: a size, a count, a mass, a volume, a composition")
    property: Property | None = Field(default=None, description="The property record, only if construction is true")


class MissedList(BaseModel):
    answers: list[Missed]


NUMBER_WORDS = {w: float(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
NUMBER_WORDS.update({"sixteen": 16.0, "twenty": 20.0, "twenty-four": 24.0})


def coverage_pass(readings, documents, detector, log=None, window=1, reader="A", per_sentence=False):
    """Numbers that no property covers, in the sentences the readers took records from and their neighbours,
    go back to one reader: is it a construction value that was missed? Returns the new Property records
    (already checked against the document). They still count as found by one reader only.
    With `per_sentence`, a number counts as covered only if a property taken from the same sentence states it
    (otherwise small numbers such as 2 or 3 are always "covered" by some other sentence), and numbers written
    as words ("three fibres", "seven strings") are looked at as well."""
    from g4geoagent.agent.compare import POINTERS
    covered = {float(n) for e in readings.values() for p in e.properties
               for n in ([p.value] if isinstance(p.value, (int, float)) else numbers_in(str(p.value)))}
    names = sorted({norm(p.name) for e in readings.values() for p in e.parts})
    items = []
    for text in documents.values():
        parts = sentences(text)
        active = set()
        for e in readings.values():
            for record in [*e.parts, *e.properties, *e.relations]:
                for i in locate(record.quote, text):
                    active.update(range(max(0, i - window), min(len(parts), i + window + 1)))
        here = {}
        if per_sentence:
            for e in readings.values():
                for p in e.properties:
                    numbers = [float(p.value)] if isinstance(p.value, (int, float)) else numbers_in(str(p.value))
                    for i in locate(p.quote, text):
                        here.setdefault(i, set()).update(numbers)
        for i in sorted(active):
            clean = POINTERS.sub(" ", REFERENCE.sub(" ", parts[i]))
            numbers = numbers_in(clean)
            if per_sentence:
                numbers += [NUMBER_WORDS[w] for w in re.findall(r"[a-z]+(?:-[a-z]+)?", clean.lower()) if w in NUMBER_WORDS and w != "one"]
            for number in dict.fromkeys(numbers):
                if number not in (here.get(i, set()) if per_sentence else covered):
                    items.append((number, parts[i]))
    added = []
    schema = json.dumps(MissedList.model_json_schema(), separators=(",", ":"))
    for start in range(0, len(items), 20):
        batch = items[start:start + 20]
        listing = "\n".join(f"{i}. the number {number:g} in: \"{sentence[:400]}\"" for i, (number, sentence) in enumerate(batch))
        request = (f"A document about the detector {detector} was read, and these numbers were not written down. For "
                   "each one decide: does it state how the detector is built (a size, a count, a mass, a volume, a "
                   "composition of a part)? If yes, give the property record: the part it belongs to, the quantity, "
                   "the value, the unit, and a quote of at most 20 exact words from the sentence that contains the "
                   "number. Parts named so far: " + ", ".join(names) + ". Numbers that are energies, rates, years, "
                   "resolutions, voltages, figure or section numbers are not construction.\n\nItems:\n" + listing
                   + "\n\nAnswer with one JSON object that fits this schema and nothing else:\n" + schema)
        try:
            answer, _ = call_llm_json(READERS[reader][0], [{"role": "user", "content": request}], MissedList, log=log,
                                      stage="graph_coverage", temperature=0)
        except ValueError:
            continue
        added += [a.property for a in answer.answers if a.construction and a.property]
    if per_sentence:                                # a count written as a word passes if the quote is in the document
        whole = _squash(REFERENCE.sub(" ", " ".join(documents.values())))
        return [p for p in added if _squash(REFERENCE.sub(" ", p.quote)) and _squash(REFERENCE.sub(" ", p.quote)) in whole]
    kept, _ = check(Extraction(parts=[], properties=added, relations=[]), documents, tolerant=True)
    return kept.properties


class Placement(BaseModel):
    item: int
    stated: bool = Field(description="true if the sentences say where the part is or what it belongs to")
    relation: Relation | None = Field(default=None, description="The relation record, only if stated is true")


class Placements(BaseModel):
    answers: list[Placement]


def placement_pass(graph, documents, detector, log=None, reader="B"):
    """For every part of which the graph does not say where it is: the sentences that mention the part go to
    one reader, who gives the relation to another part if the document states one. Returns the new Relation
    records (already checked against the document)."""
    names = [n["name"] for n in graph["nodes"]]
    lost = [n for n in graph["nodes"] if "where it is" in n["unknown"]]
    items = []
    for n in lost:
        words = {w.lower() for w in [n["name"].replace("_", " "), *n["also_called"]] if len(w) > 2}
        found = [s for text in documents.values() for s in sentences(text)
                 if any(re.sub(r"[_\-]", " ", w) in re.sub(r"[_\-]", " ", s.lower()) for w in words)]
        if found:
            items.append((n, " ".join(found[:4])[:900]))
    added = []
    schema = json.dumps(Placements.model_json_schema(), separators=(",", ":"))
    for start in range(0, len(items), 10):
        batch = items[start:start + 10]
        listing = "\n".join(f"{i}. part: {n['name']} ({n['what']})\n   sentences: \"{text}\"" for i, (n, text) in enumerate(batch))
        request = (f"These parts of the detector {detector} were found in a document, but not where they are. For each "
                   "part, read its sentences: do they say where the part is, what it is inside of, on, attached to, "
                   "next to, or what it is a component of? If yes, give one relation record between this part and "
                   "another part, with a quote of at most 20 exact words from the sentences. Use these names for the "
                   "other part where they fit: " + ", ".join(names) + ". Relations: " + ", ".join(RELATIONS) + ". "
                   "'B contains A' for A inside B; 'B consists_of A' for A a component of B. If the sentences do not "
                   "say it, answer stated = false. Do not guess.\n\nItems:\n" + listing
                   + "\n\nAnswer with one JSON object that fits this schema and nothing else:\n" + schema)
        try:
            answer, _ = call_llm_json(READERS[reader][0], [{"role": "user", "content": request}], Placements, log=log,
                                      stage="graph_placement", temperature=0)
        except ValueError:
            continue
        added += [a.relation for a in answer.answers if a.stated and a.relation]
    kept, _ = check(Extraction(parts=[], properties=[], relations=added), documents, tolerant=True)
    return kept.relations


class SameParts(BaseModel):
    same: list[list[str]] = Field(description="Groups of names from the list that are one and the same physical part")


def same_parts(graph, log=None, model="lbl/gpt-oss-120b", with_figures=False):
    """Names in the graph that mean the same part: [[name, name, ...], ...]. Asked of a model that sees every
    part with what it is and the words it was introduced with."""
    listing = "\n".join(f"- {n['name']}: {n['what']} (also called: {', '.join(n['also_called']) or '-'}; "
                        f"introduced as: \"{n['quotes'][0]['quote'][:120] if n['quotes'] else ''}\")" for n in graph["nodes"])
    seen = graph.get("seen_only_in_figures", []) if with_figures else []
    if seen:
        listing += "\nLabels read from figures of the same detector:\n" + "\n".join(f"- {s['name']}: {s['what']}" for s in seen)
    request = (f"These parts were extracted from documents about the detector {graph['detector']}, by two readers who "
               f"did not always use the same names:\n\n{listing}\n\n"
               "Which of these names are one and the same physical part under two names? For example an abbreviation "
               "and its long form, singular and plural, or the same part named once with and once without its "
               "material. Do NOT join a part with one of its components, a vessel with its filling, one item with the "
               "array of such items, or two different parts of the same kind. If in doubt, do not join. "
               'Answer with one JSON object: {"same": [["name_a", "name_b"], ...]}, with the names exactly as in the list. '
               "An empty list if there are none.")
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": request}], SameParts, log=log,
                                  stage="graph_same_parts", temperature=0)
    except ValueError:
        return []
    known = {n["name"] for n in graph["nodes"]} | {s["name"] for s in seen}
    return [[n for n in group if n in known] for group in answer.same if len([n for n in group if n in known]) > 1]


def unknown(node, graph):
    """What the graph does not say about a part and a build would need."""
    have = {p["quantity"] for p in graph["properties"] if p["of"] == node["name"] and p["built"]}
    missing = []
    filling = any(r["object"] == node["name"] and r["relation"] == "contains" for r in graph["relations"]) and \
        bool(re.search(r"water|argon|xenon|nitrogen|gas|liquid|oil|scintillator_liquid|air|vacuum|gel|ice", node["name"]))
    if filling:
        return [] if have & {"volume", "mass"} or True else []          # it fills its vessel; nothing more is needed to build it
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
    """The graph of a detector from its documents, with the set-up chosen in experiments/notes/graph.md (design 14).
    Writes graph.json, graph.txt, dropped.json and disputed.json into `folder`."""
    from g4geoagent.reviewer import look
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    documents = {Path(f).name: Path(f).read_text() for f in text_files}
    # 1. each reader reads the text twice; the records of both passes are pooled
    jobs = [(reader, seed) for reader in "AB" for seed in (None, 2)]
    with ThreadPoolExecutor(4) as pool:
        raw = list(pool.map(lambda job: read_text(documents, job[0], log, PROMPT_3, job[1]), jobs))
    readings, dropped = {}, []
    for reader in "AB":
        pooled = union(*(e for (r, _), e in zip(jobs, raw) if r == reader))
        # 2. every quote is checked against the document
        readings[reader], out = check(pooled, documents, tolerant=True)
        dropped += [{"reader": reader, **d} for d in out]
    # 3. numbers the readers left out go back to one reader
    readings["A"].properties += coverage_pass(readings, documents, detector, log)
    # 4. what only one reader has is checked by the other, twice
    readings, disputed = cross_check(readings, documents, detector, log, correct=True, votes=2)
    # 5. figures that show the construction are read by a vision model; they add to parts the text names
    if pdf:
        figures = look.extract_figures(pdf, folder / "figures")
        for figure in look.construction_figures(figures[:12], folder / "figures", detector, log, most=3):
            seen = read_figure(figure, folder / "figures", detector, log)
            if seen:
                readings[f"figure:{figure['file']}"] = seen
    # 6. one graph; then names that mean the same part are joined
    options = dict(by_family=True, figures_extend_only=True, tidy_values=True)
    graph = merge(readings, documents, detector, **options)
    graph = merge(readings, documents, detector, same=same_parts(graph, log, with_figures=True), **options)
    (folder / "graph.json").write_text(json.dumps(graph, indent=1, default=sorted))
    (folder / "graph.txt").write_text(as_text(graph) + "\n")
    (folder / "dropped.json").write_text(json.dumps(dropped, indent=1))
    (folder / "disputed.json").write_text(json.dumps(disputed, indent=1, default=sorted))
    return graph, dropped


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    files = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] != "--name"]
    graph, dropped = build_graph(args[0], [f for f in files if not f.endswith(".pdf")],
                                 next((f for f in files if f.endswith(".pdf")), None), name)
    print(as_text(graph))
    print(f"\n{len(dropped)} records dropped by the quote check")
