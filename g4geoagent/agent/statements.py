"""The claim step with free readers: a reader writes each fact as a plain sentence, with a short receipt.

    python -m g4geoagent.agent.statements <output folder> <paper.txt> [--name "LEGEND-200"]

A variant of claims.py, kept beside it. What differs:

  - A reader does not fill in a form with fixed lists of quantities, shapes and relations. It writes one sentence
    per fact in its own words, and beside it only what a program has to check: the quote, the numbers with their
    units, the parts named, the material if one is stated, and which part is inside which if the fact says so.
  - The text is read in sections of a few pages, so that a long paper is read to its end and one failed answer
    costs one section of one reader, not the paper.
  - In the cross-check the other reader may put a statement right instead of rejecting it.
  - A reader marks what it concludes without the text saying it.

The claims it writes are Claim objects as in claims.py, so the graph step takes them as they are:
  a statement with numbers or a material -> one 'value' claim that carries all its numbers
  a statement about several parts        -> a 'relation' claim with no fixed kind; the graph step reads the sentence
  a statement about one part             -> a 'feature' claim
One statement is one claim. Every claim shows its statement to the model that builds the graph, with its receipt.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from g4geoagent.agent import claims as C
from g4geoagent.agent import graph as G
from g4geoagent.agent.compare import _squash, numbers_in
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.readers import READERS

SECTION = 14000            # characters of text per call, in whole pages
PARALLEL = 6
# a number with one of these units, or with none (a count), is a construction value; others (V, K, bar, Hz ...) are not
BUILT_UNITS = re.compile(r"^(|[μµnmck]?m|mm|cm|km|[μµ]m|nm|in|inch|inches|\"|”|ft|feet|[mck]?m[2²3³]|mm[2²3³]|l|L|ml|mL|"
                         r"lit(er|re)s?|m\^?[23]|cm\^?[23]|mm\^?[23]|g|kg|mg|t|tons?|tonnes?|kton|ktons|kt|lb|lbs|%|°|◦|deg|degrees?|mrad|rad)$")
WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "hundred": 100, "twenty-four": 24, "thirty-two": 32,
              "thirty-six": 36, "forty-eight": 48, "sixty-four": 64})


class Number(BaseModel):
    value: float
    unit: str = ""


class Statement(BaseModel):
    statement: str = Field(description="The fact as one short plain sentence that can be understood on its own")
    quote: str = Field(description="The words of the document it rests on, copied exactly, short, with every number of the fact")
    parts: list[str] = Field(default_factory=list, description="The detector parts the fact is about, the main one first")
    numbers: list[Number] = Field(default_factory=list)
    material: str = ""
    outer: str = ""
    inner: str = ""
    inferred: bool = False


class Reading(BaseModel):
    statements: list[Statement]


PROMPT = """You read part of a document about the detector {detector} and write down every fact it states about how the \
detector is built: which parts it has, what they are made of or filled with, their shapes, sizes, masses and numbers, \
and how they are arranged: what is inside what, what is mounted on, attached to, next to, above, below, between or \
around what, and at which distance.

Write one short, plain sentence per fact, in your own words.
- A sentence must be understandable on its own. Name the parts in it; do not write "it" or "the latter".
- Say what the document means. A distance between two parts is a distance, not a height. A number of pieces is a \
count. A purity is not a material.
- One fact per sentence. Put several numbers into one sentence only if they are the dimensions of the same part \
("the box is 2300 mm × 2300 mm × 365 mm"). A size, a count, a material and a position of the same part are four \
sentences. Do not give as a number what is part of a name ("the 300 K plate", "the 10 mK vessel").

For each fact give:
  statement  the sentence
  quote      the words of the document it rests on, copied exactly, as short as possible, containing every number of \
the fact. No "..." and no words of your own.
  parts      the detector parts the fact is about: lower case with underscores, singular ("water_tank", "pmt"), the \
part the fact is mainly about first. Use the same name for the same part every time.
  numbers    every number of the fact with its unit, as in the quote: {{"value": 76.8, "unit": "mm"}}. A count has \
unit "". A number written as a word ("three") is given as a number.
  material   if the fact says what a part is made of or filled with: the material in the document's words. Else "".
  outer, inner   if the fact says that one part is inside another or is one of its pieces, give the containing part \
in "outer" and the contained part in "inner", named as in parts. This is so whenever the document says: comprises, \
consists of, is composed of, is made up of, contains, houses, holds, is filled with, inside, within, immersed in, \
submerged in, embedded in, enclosed in ("the reflector comprises 350 facets": outer "reflector", inner "mirror_facet"). \
It is not so for: mounted on, supported on, attached to, suspended from, next to, above, below, surrounded by a \
shield. Then leave both "".
  inferred   false if the quote says this itself. true if you conclude it and the document does not say it in so \
many words.

Facts in the abstract, the introduction and the figure captions count like those in the main text: how many \
detectors, modules or sensors there are, total masses, overall sizes.

Leave out: physics goals and results, performance figures (resolution, efficiency, rates, thresholds), operating \
values (voltages, temperatures, pressures, flows), history and schedules, other experiments and earlier versions, \
software, and electronics unless they are physical parts with a place in the detector.

{procedure}
Read all of the text. Its end matters as much as its beginning.

Answer with one JSON object {{"statements": [...]}} that fits this schema and nothing else:
{schema}"""


def sections(text, size=SECTION):
    """The text cut into pieces of whole pages, each at most about `size` characters."""
    pages = [p for p in re.split(r"\n(?=\[page \d+\])", text) if p.strip()]
    out, current = [], ""
    for page in pages:
        if current and len(current) + len(page) > size:
            out.append(current)
            current = ""
        current += ("\n" if current else "") + page
    return out + ([current] if current else [])


def read_sections(documents, reader, detector, log=None, seed=None):
    """One reader's statements for the documents, read section by section. Returns (statements, failed sections)."""
    model, procedure = READERS[reader]
    schema = json.dumps(Reading.model_json_schema(), separators=(",", ":"))
    system = PROMPT.format(detector=detector, procedure="Procedure: " + procedure.replace("Procedure: ", ""), schema=schema)
    jobs = [(name, i, piece) for name, text in documents.items() for i, piece in enumerate(sections(text))]

    def one(job):
        name, i, piece = job
        options = {} if seed is None else {"seed": seed}
        try:
            answer, _ = call_llm_json(model, [{"role": "system", "content": system},
                                              {"role": "user", "content": f"===== Document: {name}, section {i + 1} =====\n{piece}"}],
                                      Reading, log=log, stage=f"free_reader_{reader}", temperature=0, **options)
            return answer.statements, None
        except Exception as error:
            return [], f"{name} section {i + 1}: {type(error).__name__}: {str(error)[:160]}"
    with ThreadPoolExecutor(PARALLEL) as pool:
        results = list(pool.map(one, jobs))
    return [s for found, _ in results for s in found], [problem for _, problem in results if problem]


def stated_numbers(text):
    """The numbers in a piece of text, digits and number words."""
    words = [float(WORDS[w]) for w in re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower()) if w in WORDS]
    return [float(n) for n in numbers_in(text)] + words + ([2.0] if re.search(r"\b(a couple|a pair|both|double)\b", text.lower()) else [])


def check(statements, documents):
    """The quote check. Returns (kept statements, dropped records with the reason).
    A quote must be in the documents; reference marks such as [8] are ignored, and a quote that is not found as a
    whole is cut down to its longest part that is. Every number of a statement must be in its quote, as digits or
    as a word, unless the reader marked the statement as its own conclusion."""
    whole = _squash(G.REFERENCE.sub(" ", " ".join(documents.values())))
    kept, dropped = [], []
    for s in statements:
        s.quote = G.REFERENCE.sub(" ", s.quote)
        problem = "" if _squash(s.quote) and _squash(s.quote) in whole else "quote is not in the document"
        if problem:
            shorter = G._repair(s.quote, whole, s.numbers[0].value if s.numbers else None)
            if shorter:
                s.quote, problem = shorter, ""
        if not problem and not s.inferred:
            there = stated_numbers(s.quote)
            missing = [n for n in s.numbers if not any(abs(n.value - t) <= 1e-9 * max(abs(t), 1) for t in there)]
            if missing and len(missing) == len(s.numbers):
                problem = f"quote does not contain the number {missing[0].value:g}"
            elif missing:                       # the numbers that the quote does hold are kept, the others are taken off
                dropped.append({"problem": f"quote does not contain the number {missing[0].value:g}; the statement is kept without it",
                                **s.model_copy(update={"numbers": missing}).model_dump()})
                s.numbers = [n for n in s.numbers if n not in missing]
        if not problem and not s.statement.strip():
            problem = "no statement"
        (dropped.append({"problem": problem, **s.model_dump()}) if problem else kept.append(s))
    return kept, dropped


def pool(readings, documents):
    """The statements of all readers, the same fact once. Two statements are the same fact if they rest on the same
    sentence and give the same numbers or, without numbers, name the same two parts.
    readings: {reader: [Statement]}. Returns a list of {"s": Statement, "found_by": [readers], "sentence": ..., ...}."""
    found = {}
    for reader, statements in readings.items():
        for s in statements:
            place = G._sentence(s.quote, documents)
            numbers = tuple(sorted(round(n.value, 9) for n in s.numbers))
            ends = (G.norm(s.outer), G.norm(s.inner)) if s.outer and s.inner else tuple(sorted(G.norm(p) for p in s.parts[:2]))
            key = (_squash(place["sentence"]) or _squash(s.quote), numbers, () if numbers else ends, _squash(s.material))
            entry = found.setdefault(key, {"s": s, "found_by": [], "checks": ["quote is in the document"], "status": "accepted", **place})
            if reader not in entry["found_by"]:
                entry["found_by"].append(reader)
            if s.outer and s.inner:
                entry.setdefault("inside_by", set()).add(reader)
    return list(found.values())


class Verdict(BaseModel):
    item: int
    verdict: str = Field(description="right, wrong, not_construction or corrected")
    statement: str = ""
    parts: list[str] = Field(default_factory=list)
    numbers: list[Number] = Field(default_factory=list)
    material: str = ""
    outer: str = ""
    inner: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict]


def cross_check(entries, documents, detector, log=None, trusted=("B",)):
    """Every statement that only one reader has goes to the other reader, with the sentence it was taken from.
    The other reader answers right, wrong, not_construction, or corrected with the statement put right. A corrected
    statement passes the quote check again, against the sentence, and replaces the first one.
    A statement of a `trusted` reader is not taken out or changed on the other reader's word; it is marked as questioned.
    Changes the entries in place and returns the entries that were taken out or replaced."""
    removed = []
    for reader, other in (("A", "B"), ("B", "A")):
        single = [e for e in entries if e["found_by"] == [reader] and e["status"] == "accepted"]
        batches = [single[i:i + 20] for i in range(0, len(single), 20)]

        def ask(batch):
            items = "\n".join(f"{i}. {e['s'].statement}\n   sentence: \"{(e['sentence'] or e['s'].quote)[:500]}\"" for i, e in enumerate(batch))
            request = (f"Another reader wrote these statements about how the detector {detector} is built. Check each one "
                       "against the sentence of the document it was taken from.\n"
                       "- 'right': the sentence says this.\n"
                       "- 'corrected': the sentence is about how the detector is built, but the statement gets it wrong: the "
                       "number belongs to another part or means something else (a distance, not a height), or the parts are "
                       "related in another way. Give the statement put right, with its parts (lower case with underscores, the "
                       "main one first), its numbers with units, material, and outer / inner if one part is inside another. "
                       "Prefer this over 'wrong' whenever the sentence does state a construction fact with these numbers or parts.\n"
                       "- 'not_construction': the sentence says it, but it is a physics result, a performance figure or an "
                       "operating value, not how the detector is built.\n"
                       "- 'wrong': the sentence says nothing of the kind.\n\nItems:\n" + items
                       + '\n\nAnswer with one JSON object: {"verdicts": [{"item": 0, "verdict": "right"}, {"item": 1, "verdict": '
                         '"corrected", "statement": "...", "parts": ["..."], "numbers": [{"value": 1.0, "unit": "mm"}], '
                         '"material": "", "outer": "", "inner": ""}, ...]}')
            try:
                answer, _ = call_llm_json(READERS[other][0], [{"role": "user", "content": request}], Verdicts, log=log,
                                          stage=f"free_cross_check_{other}", temperature=0)
                return {v.item: v for v in answer.verdicts}
            except Exception:
                return {}
        with ThreadPoolExecutor(PARALLEL) as pool_:
            answers = list(pool_.map(ask, batches))
        for batch, verdicts in zip(batches, answers):
            for i, e in enumerate(batch):
                v = verdicts.get(i)
                word = (v.verdict.strip().lower() if v else "")
                if word == "right":
                    e["found_by"].append(other)
                    e["checks"].append("confirmed by the other reader")
                elif not v or word not in ("wrong", "not_construction", "corrected"):
                    e["checks"].append("not cross-checked: the other reader gave no verdict")
                elif reader in trusted:
                    e["checks"].append(f"questioned by the other reader ('{word}'); kept, because the reader who found it is the more reliable one")
                elif word == "corrected" and v.statement.strip():
                    new = Statement(statement=v.statement, quote=e["sentence"] or e["s"].quote, parts=v.parts or e["s"].parts,
                                    numbers=v.numbers, material=v.material, outer=v.outer, inner=v.inner)
                    kept, _ = check([new], documents)
                    if kept:
                        removed.append({**e, "status": "disputed", "checks": e["checks"] + [f"put right by the other reader: {v.statement}"]})
                        e["s"], e["found_by"] = kept[0], [reader, other]
                        e["checks"] = ["quote is in the document", f"put right by the other reader; first written as: {removed[-1]['s'].statement}"]
                    else:
                        e["status"] = "disputed"
                        e["checks"].append("judged wrong by the other reader; its correction did not pass the quote check: " + v.statement)
                else:
                    e["status"] = "disputed"
                    e["checks"].append(f"judged '{word}' by the other reader")
    return removed


def to_claims(entries, dropped, documents, origin="starting document"):
    """Claim objects (claims.py) from the pooled statements and from what the quote check dropped: one claim per
    statement. A statement with numbers or a material is a 'value' claim that carries all its numbers; one about
    several parts without numbers is a 'relation' claim; one about a single part is a 'feature' claim.
    "outer contains inner" is passed on only if both readers wrote it for this statement."""
    claims = []

    def add(s, status, checks, found_by, place, inside=True):
        main = s.parts[0] if s.parts else (s.outer or s.inner)
        fields = {"statement": s.statement, "quote": s.quote, "parts": s.parts, "inferred": s.inferred, "status": status,
                  "checks": checks, "found_by": found_by, "origin": origin, "file": place.get("file", ""),
                  "page": place.get("page"), "sentence": place.get("sentence", ""), "subject": main,
                  "material": s.material.strip()}
        if inside and s.outer.strip() and s.inner.strip() and G.norm(s.outer) != G.norm(s.inner):
            fields.update(outer=s.outer, inner=s.inner)
        several = len({G.norm(p) for p in s.parts}) >= 2
        if s.numbers:
            one = len(s.numbers) == 1
            fields.update(kind="value", wording="exact", built=any(BUILT_UNITS.match(n.unit.strip()) for n in s.numbers),
                          value=s.numbers[0].value if one else ", ".join(f"{n.value:g} {n.unit}".strip() for n in s.numbers),
                          unit=s.numbers[0].unit if one else "")
        elif s.material.strip():
            fields.update(kind="value", quantity="material", value=s.material.strip(), built=True)
        elif several or "outer" in fields:
            fields.update(kind="relation", relation="contains" if "outer" in fields else "",
                          subject=fields.get("outer", main), object=fields.get("inner") or next(p for p in s.parts if G.norm(p) != G.norm(main)))
        else:
            fields.update(kind="feature", text=s.statement)
        claims.append(C.Claim(id=f"K{len(claims) + 1}", **fields))

    for e in entries:
        if e["status"] == "accepted":
            if e["s"].inferred:
                e["checks"].append("concluded by the reader, not stated in so many words")
            both = len(e.get("inside_by", ())) >= 2
            if e["s"].outer and e["s"].inner and not both:
                e["checks"].append(f"only one reader gave '{e['s'].outer} contains {e['s'].inner}'; not passed on as a stated containment")
            add(e["s"], "accepted", e["checks"], e["found_by"], e, inside=both)
    for e in entries:
        if e["status"] != "accepted":
            add(e["s"], "disputed", e["checks"], e["found_by"], e)
    for d in dropped:
        add(Statement(**{k: v for k, v in d.items() if k in Statement.model_fields}), "dropped", [d["problem"]], [d.get("reader", "")], {})
    return claims


def claim_step(folder, text_files, detector="detector", log=None, origin="starting document", figures=None):
    """Read the documents into claims with the free readers and save them. Returns the list of Claim."""
    from g4geoagent.reviewer import look
    folder = Path(folder)
    documents = {Path(f).name: Path(f).read_text() for f in text_files}
    jobs = [(reader, seed) for reader in "AB" for seed in (None, 2)]             # each reader reads twice
    with ThreadPoolExecutor(4) as pool_:
        answers = list(pool_.map(lambda job: read_sections(documents, job[0], detector, log, job[1]), jobs))
    readings, dropped, failed = {}, [], []
    for reader in "AB":
        statements = [s for (r, _), (found, _) in zip(jobs, answers) if r == reader for s in found]
        failed += [f"reader {r}{'' if seed is None else ', second pass'}: {p}" for (r, seed), (_, problems) in zip(jobs, answers) if r == reader for p in problems]
        readings[reader], out = check(statements, documents)
        dropped += [{"reader": reader, **d} for d in out]
    entries = pool(readings, documents)
    replaced = cross_check(entries, documents, detector, log)
    claims = to_claims(entries + replaced, dropped, documents, origin)
    if figures:
        for figure in look.construction_figures(figures[0][:12], figures[1], detector, log, most=3):
            seen = G.read_figure(figure, figures[1], detector, log)
            if seen:
                for c in C.ledger({f"figure:{figure['file']}": seen}, [], [], documents, origin):
                    c.id = f"K{len(claims) + 1}"
                    claims.append(c)
    C.save(claims, folder)
    (folder / "reading.json").write_text(json.dumps({"sections": sum(len(sections(t)) for t in documents.values()),
                                                     "failed_sections": failed}, indent=1))
    return claims


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    files = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] != "--name"]
    claim_step(args[0], files, name)
    print((Path(args[0]) / "claims.txt").read_text())
