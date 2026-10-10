"""From two independent readings to one list of agreed claims.

1. Each reader reads the documents (readers.read_paper).
2. A program checks every quote. A reader gets one chance to repair a quote
   that fails; claims that still fail are dropped.
3. A program pairs up the claims of the two readers. Paired claims are agreed.
4. A claim that only one reader has goes to the other reader, who confirms or
   rejects it. Rejected claims are kept apart as disputed.
"""

import json
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from g4geoagent.agent import readers
from g4geoagent.agent.compare import (check_quotes, claim_numbers, closest_sentences, locate,
                                       match_readings, sentences)
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.schemas import Checks, Claim, Reading, Repairs

BATCH = 20


class Agreed(BaseModel):
    reading: Reading                      # agreed claims: found by both readers, or by one and confirmed by the other
    disputed: list[Claim] = []            # found by one reader and rejected by the other
    dropped: list[Claim] = []             # quote could not be verified
    counts: dict = {}


def _ask(reader, schema, system, request, log, stage):
    model, _ = readers.READERS[reader]
    text = request + "\n\nAnswer with one JSON object that fits this schema and nothing else:\n" + \
        json.dumps(schema.model_json_schema(), separators=(",", ":"))
    answer, _ = call_llm_json(model, [{"role": "system", "content": system}, {"role": "user", "content": text}],
                              schema, log=log, stage=stage, temperature=0)
    return answer


def repair_quotes(reading, documents, reader, log=None):
    """Give the reader one chance to fix quotes that fail the check. Returns the claims that were dropped."""
    failing = check_quotes(reading, documents)
    dropped = []
    for start in range(0, len(failing), BATCH):
        batch = failing[start:start + BATCH]
        items = []
        for i, (claim, problem) in enumerate(batch):
            offered = closest_sentences(claim, documents.get(claim.source, ""))
            items.append(f"{i}. {claim.part} {claim.quantity} = {claim.value} {claim.unit}\n   your quote: \"{claim.quote}\"\n"
                         f"   problem: {problem}\n   closest sentences in the document:\n" +
                         "\n".join(f"     - \"{s[:500]}\"" for s in offered))
        try:
            answer = _ask(reader, Repairs,
                          "You extracted claims from a document. A program could not verify some of your quotes. "
                          "For each item, copy the exact wording that states the value from one of the offered "
                          "sentences, character by character and without joining passages. If none of the "
                          "sentences states the value, give an empty quote to withdraw the claim.",
                          "Items:\n" + "\n".join(items), log, f"reader_{reader}_repair")
            fixed = {r.item: r.quote for r in answer.repairs}
        except ValueError:
            fixed = {}
        for i, (claim, _) in enumerate(batch):
            claim.quote = fixed.get(i, "") or claim.quote
        still = {id(c) for c, _ in check_quotes(Reading(parts=[], claims=[c for c, _ in batch]), documents)}
        dropped += [c for c, _ in batch if id(c) in still or not fixed.get(i_of(batch, c))]
    reading.claims = [c for c in reading.claims if not any(c is d for d in dropped)]
    if log:
        log.event("quote_repair", f"reader_{reader}", failing=len(failing), dropped=len(dropped))
    return dropped


def i_of(batch, claim):
    return next(i for i, (c, _) in enumerate(batch) if c is claim)


def cross_check(claims, documents, reader, log=None):
    """Ask `reader` about claims that only the other reader made. Returns (confirmed, rejected)."""
    confirmed, rejected = [], []
    for start in range(0, len(claims), BATCH):
        batch = claims[start:start + BATCH]
        items = []
        for i, claim in enumerate(batch):
            text = documents.get(claim.source, "")
            parts = sentences(text)
            context = " ".join(parts[j] for j in sorted(locate(claim.quote, text)))[:700]
            items.append(f"{i}. claim: {claim.part} / {claim.quantity} = {claim.value} {claim.unit} ({claim.category})\n"
                         f"   sentence: \"{context}\"")
        try:
            answer = _ask(reader, Checks,
                          "Another reader extracted claims about how a particle detector is physically built "
                          "(parts, dimensions, counts, materials, positions, masses, volumes). Check each claim "
                          "against the sentence it was taken from.\n- `confirmed`: the sentence states this, and it "
                          "is about the detector hardware.\n- `wrong`: the sentence does not say this.\n"
                          "- `not_construction`: it is a physics result, a performance figure, a date or similar.",
                          "Items:\n" + "\n".join(items), log, f"reader_{reader}_cross_check")
            verdicts = {c.item: c.verdict for c in answer.checks}
        except ValueError:
            verdicts = {}
        for i, claim in enumerate(batch):
            (confirmed if verdicts.get(i, "confirmed") == "confirmed" else rejected).append(claim)
    if log:
        log.event("cross_check", f"reader_{reader}", asked=len(claims), confirmed=len(confirmed), rejected=len(rejected))
    return confirmed, rejected


def agreed_reading(documents, log=None, check=True):
    """The agreed claims of the two readers. With check=False, single-reader claims are accepted unchecked."""
    with ThreadPoolExecutor(2) as pool:
        a, b = pool.map(lambda name: readers.read_paper(documents, name, log), "AB")
    dropped = repair_quotes(a, documents, "A", log) + repair_quotes(b, documents, "B", log)
    pairs, only_a, only_b = match_readings(a, b, documents)
    if check:
        confirmed_a, rejected_a = cross_check(only_a, documents, "B", log)
        confirmed_b, rejected_b = cross_check(only_b, documents, "A", log)
    else:
        confirmed_a, rejected_a, confirmed_b, rejected_b = only_a, [], only_b, []
    parts = {p.name: p for p in a.parts + b.parts}
    claims, category_conflicts = [], 0
    for first, second in pairs:
        if (first.category == "not_geometry") != (second.category == "not_geometry"):
            # the readers disagree on whether this is built: keep it as built, so that it is not lost
            category_conflicts += 1
            first, second = (second, first) if first.category == "not_geometry" else (first, second)
        claims.append(first)
        if set(claim_numbers(second)) - set(claim_numbers(first)):     # the other reader's claim says more
            claims.append(second)
    claims += confirmed_a + confirmed_b
    counts = {"reader_a": len(a.claims), "reader_b": len(b.claims), "both": len(pairs),
              "only_one_confirmed": len(confirmed_a) + len(confirmed_b),
              "disputed": len(rejected_a) + len(rejected_b), "dropped": len(dropped),
              "category_conflicts": category_conflicts}
    if log:
        log.event("agreed", "compare", **counts)
    return Agreed(reading=Reading(parts=list(parts.values()), claims=claims, gaps=a.gaps + b.gaps),
                  disputed=rejected_a + rejected_b, dropped=dropped, counts=counts)
