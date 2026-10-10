"""The reading step: turn the documents of a task into claims.

Two readers work independently, with different models and a different way of
going through the text, so that they do not make the same mistakes.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import re

from g4geoagent.agent.compare import NUMBER, uncovered_near_claims, uncovered_numbers
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.schemas import MoreClaims, Outline, Reading, Verdicts

PROMPTS = Path(__file__).parent / "prompts"
PROMPT = (PROMPTS / "reader.md").read_text()                 # complete descriptions: every number is a claim
PAPER_PROMPT = (PROMPTS / "reader_paper.md").read_text()     # papers: only what describes the construction
TEXT_SUFFIXES = {".md", ".txt"}
WHOLE_LIMIT = 7000      # words: longer documents are read in pieces
PIECE_WORDS = 3000
VERDICT_BATCH = 25

# name: (model, how this reader goes through the text)
READERS = {
    "A": ("lbl/gpt-oss-120b",
          "Procedure: go through the documents sentence by sentence, in order. For each "
          "sentence write the claims it contains before moving on."),
    "B": ("lbl/gemma-4",
          "Procedure: first list the parts. Then take one part at a time and collect "
          "everything the documents say about it. At the end, go through the documents "
          "once more and check that no number was left out."),
}


def load_documents(folder):
    """{file name: text} for every text document in `folder`."""
    files = sorted(p for p in Path(folder).iterdir() if p.suffix in TEXT_SUFFIXES)
    return {p.name: p.read_text() for p in files}


def read(documents, reader, log=None, prompt=PROMPT, extra=""):
    """One reader's Reading of `documents` ({file name: text}). `extra` is added to the instructions."""
    model, procedure = READERS[reader]
    procedure = f"{procedure}\n\n{extra}".strip()
    schema = json.dumps(Reading.model_json_schema(), separators=(",", ":"))
    text = "\n\n".join(f"===== Document: {name} =====\n{body}" for name, body in documents.items())
    messages = [{"role": "system", "content": prompt.format(procedure=procedure, schema=schema)},
                {"role": "user", "content": text}]
    reading, _ = call_llm_json(model, messages, Reading, log=log, stage=f"reader_{reader}", temperature=0)
    if log:
        for claim in reading.claims:
            log.event("claim", f"reader_{reader}", **claim.model_dump())
        for gap in reading.gaps:
            log.event("gap", f"reader_{reader}", **gap.model_dump())
    return reading


def _sentences_with(number, documents):
    """The sentences of the documents in which `number` appears."""
    found = []
    for text in documents.values():
        for sentence in re.split(r"(?<=[.:;])\s+|\n\s*\n", text):
            if any(float(n) == number for n in NUMBER.findall(sentence)):
                found.append(" ".join(sentence.split()))
    return found


def read_with_coverage(documents, reader, log=None, rounds=2):
    """Read, then send back the numbers that no claim covers, up to `rounds` times."""
    reading = read(documents, reader, log)
    model, _ = READERS[reader]
    text = "\n\n".join(f"===== Document: {name} =====\n{body}" for name, body in documents.items())
    schema = json.dumps(MoreClaims.model_json_schema(), separators=(",", ":"))
    for round_number in range(rounds):
        missing = uncovered_numbers(reading, documents)
        if not missing:
            break
        listing = "\n".join(f"- {number:g}, in: \"{sentence}\""
                            for number in missing for sentence in _sentences_with(number, documents))
        request = ("A program compared your claims with the documents. These numbers appear in the "
                   "documents but are not the value of any claim:\n" + listing + "\n\n"
                   "Write one claim for each of them, following the same rules. If a number is already "
                   "inside the text value of one of your claims, it still needs its own claim. "
                   "Answer with one JSON object that fits this schema and nothing else:\n" + schema)
        messages = [{"role": "system", "content": PROMPT.format(procedure="", schema="(given below)")},
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": reading.model_dump_json()},
                    {"role": "user", "content": request}]
        stage = f"reader_{reader}_reread_{round_number + 1}"
        more, _ = call_llm_json(model, messages, MoreClaims, log=log, stage=stage, temperature=0)
        if log:
            log.event("reread", stage, missing=missing, added=len(more.claims))
            for claim in more.claims:
                log.event("claim", stage, **claim.model_dump())
        reading.claims += more.claims
    return reading


def read_twice(documents, log=None):
    """Both readers, in parallel. Returns {"A": Reading, "B": Reading}."""
    with ThreadPoolExecutor(len(READERS)) as pool:
        readings = pool.map(lambda name: read(documents, name, log), READERS)
        return dict(zip(READERS, readings))


def _pieces(text):
    """Split a long document at its page markers into pieces of about PIECE_WORDS words."""
    pages = re.split(r"(?=\[page \d+\])", text)
    pieces, current = [], ""
    for page in pages:
        if current and len((current + page).split()) > PIECE_WORDS:
            pieces.append(current)
            current = ""
        current += page
    return pieces + [current] if current.strip() else pieces


def _outline(documents, reader, log):
    """The parts of the detector, from one look at the whole text."""
    model, _ = READERS[reader]
    text = "\n\n".join(f"===== Document: {name} =====\n{body}" for name, body in documents.items())
    schema = json.dumps(Outline.model_json_schema(), separators=(",", ":"))
    messages = [{"role": "system", "content":
                 "List the physical parts of the particle detector described in the documents: the main "
                 "structures and components, and what each one sits inside. Give each part a short name in "
                 "lower case with underscores. List hardware only, at most 40 parts. Answer with one JSON "
                 "object that fits this schema and nothing else:\n" + schema},
                {"role": "user", "content": text}]
    outline, _ = call_llm_json(model, messages, Outline, log=log, stage=f"reader_{reader}_outline", temperature=0)
    return outline.parts


def verdicts_near_claims(reading, documents, reader, log=None, window=1):
    """Ask the reader about numbers it left out in the text around its claims.

    For each such number the reader says whether it is a construction value it
    missed, and then gives the claim, or not about construction. Adds the new
    claims to `reading` and returns the number of items that were asked about.
    """
    items = uncovered_near_claims(reading, documents, window)
    for start in range(0, len(items), VERDICT_BATCH):       # short lists get more careful answers
        _verdict_batch(reading, documents, reader, items[start:start + VERDICT_BATCH], log)
    return len(items)


def _verdict_batch(reading, documents, reader, items, log):
    model, _ = READERS[reader]
    listing = "\n".join(f"{i}. the number {number:g} in: \"{sentence[:400]}\"" for i, (number, sentence) in enumerate(items))
    source = next(iter(documents))
    schema = json.dumps(Verdicts.model_json_schema(), separators=(",", ":"))
    messages = [{"role": "system", "content": PAPER_PROMPT.format(procedure="", schema="(given below)")},
                {"role": "user", "content":
                 "You have already extracted claims from a document. A program found numbers that have no "
                 "claim, in sentences next to your claims. Decide for each item:\n"
                 "- `missed_value`: it states how the detector is built (a dimension, count, mass, volume, "
                 "composition or position of a part). Then give the claim, following the rules above.\n"
                 "- `not_construction`: anything else. Give no claim.\n\n"
                 f"The document is called {source}. The parts you named so far: "
                 f"{', '.join(sorted({c.part for c in reading.claims}))}.\n\nItems:\n{listing}\n\n"
                 "Answer with one JSON object that fits this schema and nothing else:\n" + schema}]
    stage = f"reader_{reader}_verdicts"
    answer, _ = call_llm_json(model, messages, Verdicts, log=log, stage=stage, temperature=0)
    added = [v.claim for v in answer.verdicts if v.verdict == "missed_value" and v.claim]
    if log:
        log.event("verdicts", stage, asked=len(items), missed_value=len(added),
                  numbers=[number for number, _ in items])
        for claim in added:
            log.event("claim", stage, **claim.model_dump())
    reading.claims += added


def _read_piece(job, reader, log):
    """Read one piece of a long document. A piece that fails is logged and left out."""
    documents, names = job
    try:
        return read(documents, reader, log, prompt=PAPER_PROMPT, extra=names)
    except Exception as error:
        if log:
            log.event("piece_failed", f"reader_{reader}", words=sum(len(t.split()) for t in documents.values()),
                      error=f"{type(error).__name__}: {str(error)[:300]}")
        return None


def read_paper(documents, reader, log=None, coverage=True, whole_limit=WHOLE_LIMIT, window=1):
    """Read papers: only what describes the construction. Long documents are read in pieces.

    With `coverage`, the reader is then asked once about numbers it left out near its claims.
    """
    words = sum(len(text.split()) for text in documents.values())
    if words <= whole_limit:
        reading = read(documents, reader, log, prompt=PAPER_PROMPT)
    else:
        parts = _outline(documents, reader, log)
        names = "Use these names for the parts where they fit: " + ", ".join(p.name for p in parts) + "."
        jobs = [({name: piece}, names) for name, text in documents.items() for piece in _pieces(text)]
        with ThreadPoolExecutor(4) as pool:
            readings = [r for r in pool.map(lambda job: _read_piece(job, reader, log), jobs) if r]
        known = {p.name for p in parts}
        for piece in readings:
            parts += [p for p in piece.parts if p.name not in known]
            known.update(p.name for p in piece.parts)
        reading = Reading(parts=parts, claims=[c for r in readings for c in r.claims],
                          gaps=[g for r in readings for g in r.gaps])
    if coverage:
        verdicts_near_claims(reading, documents, reader, log, window)
    return reading
