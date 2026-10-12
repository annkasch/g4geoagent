"""The claim step: every fact the documents state about how the detector is built, one claim per fact.

    python -m g4geoagent.agent.claims <output folder> <paper.txt> [<paper.pdf>] [--name "LEGEND-200"]

A claim only records. It keeps the names the readers took from the document, joins nothing and decides
nothing: that is the work of the graph step (detector_graph.py). Five kinds of claim:

    part      that a part exists, and what it is
    value     a size, mass, volume, count or material of a part
    shape     the shape of a part
    feature   a descriptive word about how a part is built ("vacuum-insulated", "domed ends")
    relation  how two parts are arranged

Every claim is written to claims.jsonl with its source (file, page, sentence, quote, text or figure),
who found it, and every check it went through. Claims that failed a check are kept, with the reason.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from g4geoagent.agent import graph as G
from g4geoagent.agent.compare import _squash


class Claim(BaseModel):
    id: str
    kind: Literal["part", "value", "shape", "feature", "relation"]
    subject: str = Field(description="The part the claim is about, named as the reader took it from the document")
    text: str = Field(default="", description="part: what it is. shape: the shape. feature: the descriptive words")
    # value
    quantity: str = ""
    which: str = ""
    value: float | str | None = None
    unit: str = ""
    wording: str = ""
    built: bool = True
    # relation
    relation: str = ""
    object: str = ""
    count: int | None = None
    # where it comes from
    about: str = ""
    quote: str = ""
    file: str = ""
    page: int | None = None
    sentence: str = ""
    where: Literal["text", "figure"] = "text"
    origin: str = "starting document"
    found_by: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    status: Literal["accepted", "disputed", "dropped"] = "accepted"

    def line(self):
        """The claim as one line of text, for a model."""
        if self.kind == "part":
            body = f"part {self.subject}: {self.text}"
        elif self.kind == "shape":
            body = f"shape of {self.subject}: {self.text}"
        elif self.kind == "feature":
            body = f"feature of {self.subject}: {self.text}"
        elif self.kind == "value":
            which = f" ({self.which})" if self.which and self.which != "not_stated" else ""
            wording = "" if self.wording in ("", "exact") else self.wording.replace("_", " ") + " "
            body = (f"{self.subject}: {self.quantity}{which} = {wording}{self.value} {self.unit}".strip()
                    + ("" if self.built else "  [not geometry]"))
        else:
            body = f"{self.subject} {self.relation.replace('_', ' ')} {self.object}" + (f" (x{self.count})" if self.count else "")
        source = "figure" if self.where == "figure" else f"\"{' '.join(self.quote.split())[:110]}\""
        return f"{self.id} | {body} | {source}"


def _records(extraction):
    """The records of a reading as claim fields, without id and source."""
    for part in extraction.parts:
        base = {"subject": part.name, "about": part.about, "quote": part.quote}
        yield {**base, "kind": "part", "text": part.what + (f" (also called: {', '.join(part.also_called)})" if part.also_called else "")}
        if part.shape not in ("not_stated", "other"):
            yield {**base, "kind": "shape", "text": part.shape}
        for feature in part.features:
            yield {**base, "kind": "feature", "text": feature}
    for p in extraction.properties:
        yield {"kind": "value", "subject": p.of, "quantity": p.quantity if p.quantity != "other" else p.quantity_other,
               "which": p.which, "value": p.value, "unit": p.unit, "wording": p.wording, "built": p.built,
               "about": p.about, "quote": p.quote}
    for r in extraction.relations:
        yield {"kind": "relation", "subject": r.subject, "relation": r.relation, "object": r.object, "count": r.count,
               "about": r.about, "quote": r.quote}


def _key(fields):
    return (fields["kind"], G.norm(fields["subject"]), _squash(str(fields.get("text", ""))), str(fields.get("quantity", "")),
            _squash(str(fields.get("value", ""))), fields.get("relation", ""), G.norm(fields.get("object", "")))


def _same_fact(fields, documents):
    """A key under which two readers' records are the same fact even if they name the part differently:
    the same number, or the same kind of relation, taken from the same sentence."""
    place = G._sentence(fields.get("quote", ""), documents)["sentence"]
    if not place:
        return None
    if fields["kind"] == "value" and isinstance(fields.get("value"), (int, float)):
        return ("value", _squash(place), round(float(fields["value"]), 6), fields.get("quantity", ""))
    if fields["kind"] == "relation":
        ends = sorted((G.norm(fields["subject"])[:6], G.norm(fields["object"])[:6]))
        return ("relation", _squash(place), G.FAMILY.get(fields["relation"], fields["relation"]), *ends)
    return None


def ledger(readings, dropped, disputed, documents, origin="starting document", join_same_facts=False):
    """All claims of one set of documents, from the checked readings ({reader: Extraction}; a reader named
    'figure:<file>' is a figure), the records the quote check dropped and the ones the cross-check disputed."""
    found = {}
    text_readers = sorted(r for r in readings if not r.startswith("figure"))
    for reader, extraction in readings.items():
        for fields in _records(extraction):
            key = (join_same_facts and not reader.startswith("figure") and _same_fact(fields, documents)) or _key(fields)
            entry = found.setdefault(key, {**fields, "found_by": []})
            if reader not in entry["found_by"]:
                entry["found_by"].append(reader)
            if G.norm(fields["subject"]) != G.norm(entry["subject"].split(" / ")[0]) and fields["subject"] not in entry["subject"].split(" / "):
                entry["subject"] += " / " + fields["subject"]         # the same fact under another name for the part
    claims = []

    def add(fields, status, checks):
        figure = any(r.startswith("figure") for r in fields.get("found_by", [])) and not any(r in text_readers for r in fields.get("found_by", []))
        place = {"file": fields["found_by"][0].split(":", 1)[1], "page": None, "sentence": ""} if figure else G._sentence(fields.get("quote", ""), documents)
        claims.append(Claim(id=f"K{len(claims) + 1}", status=status, checks=checks, origin=origin,
                            where="figure" if figure else "text",
                            **{k: v for k, v in fields.items() if k in Claim.model_fields and k not in ("id", "status", "checks", "origin", "where", "file", "page", "sentence")},
                            **place))

    for fields in found.values():
        if any(r.startswith("figure") for r in fields["found_by"]) and not any(r in text_readers for r in fields["found_by"]):
            add(fields, "accepted", ["read from a figure by one model, not cross-checked"])
        else:
            both = all(r in fields["found_by"] for r in text_readers)
            add(fields, "accepted", ["quote is in the document", "found or confirmed by both readers" if both
                                     else "found by one reader, not rejected by the other"])
    for record in disputed:
        fields = {"kind": "value" if record["kind"] == "property" else "relation", "subject": record.get("of", record.get("subject", "")),
                  "quantity": record.get("quantity", ""), "value": record.get("value"), "unit": record.get("unit", ""),
                  "relation": record.get("relation", "") if record["kind"] == "relation" else "", "object": record.get("object", ""),
                  "about": record.get("about", ""), "quote": record.get("quote", ""), "found_by": [record.get("reader", "")]}
        add(fields, "disputed", ["quote is in the document", f"judged '{record.get('verdict', 'wrong')}' by the other reader, twice"])
    for record in dropped:
        kind = {"parts": "part", "properties": "value", "relations": "relation"}[record["kind"]]
        fields = {"kind": kind, "subject": record.get("name", record.get("of", record.get("subject", ""))),
                  "text": record.get("what", ""), "quantity": record.get("quantity", ""), "value": record.get("value"),
                  "unit": record.get("unit", ""), "relation": record.get("relation", "") if kind == "relation" else "",
                  "object": record.get("object", ""), "about": record.get("about", ""), "quote": record.get("quote", ""),
                  "found_by": [record.get("reader", "")]}
        add(fields, "dropped", [record["problem"]])
    return claims


def save(claims, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "claims.jsonl").write_text("".join(c.model_dump_json() + "\n" for c in claims))
    accepted = [c for c in claims if c.status == "accepted"]
    lines = [f"{len(accepted)} accepted claims, {sum(c.status == 'disputed' for c in claims)} disputed, "
             f"{sum(c.status == 'dropped' for c in claims)} dropped", ""]
    for kind in ("part", "shape", "feature", "value", "relation"):
        lines += [f"--- {kind}"] + [c.line() + f" | {', '.join(c.found_by)}" for c in accepted if c.kind == kind] + [""]
    lines += ["--- disputed and dropped"] + [f"{c.line()} | {c.status}: {c.checks[-1]}" for c in claims if c.status != "accepted"]
    (folder / "claims.txt").write_text("\n".join(lines) + "\n")


def load(folder):
    return [Claim.model_validate_json(line) for line in (Path(folder) / "claims.jsonl").read_text().splitlines()]


def claim_step(folder, text_files, pdf=None, detector="detector", log=None, origin="starting document"):
    """Read the documents into claims and save them. Returns the list of Claim."""
    from g4geoagent.reviewer import look
    folder = Path(folder)
    documents = {Path(f).name: Path(f).read_text() for f in text_files}
    jobs = [(reader, seed) for reader in "AB" for seed in (None, 2)]           # each reader reads twice
    with ThreadPoolExecutor(4) as pool:
        raw = list(pool.map(lambda job: G.read_text(documents, job[0], log, G.PROMPT_3, job[1]), jobs))
    readings, dropped = {}, []
    for reader in "AB":
        readings[reader], out = G.check(G.union(*(e for (r, _), e in zip(jobs, raw) if r == reader)), documents, tolerant=True)
        dropped += [{"reader": reader, **d} for d in out]
    readings["A"].properties += G.coverage_pass(readings, documents, detector, log)
    readings, disputed = G.cross_check(readings, documents, detector, log, correct=True, votes=2)
    if pdf:
        figures = look.extract_figures(pdf, folder / "figures")
        for figure in look.construction_figures(figures[:12], folder / "figures", detector, log, most=3):
            seen = G.read_figure(figure, folder / "figures", detector, log)
            if seen:
                readings[f"figure:{figure['file']}"] = seen
    claims = ledger(readings, dropped, disputed, documents, origin)
    save(claims, folder)
    return claims


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args[args.index("--name") + 1] if "--name" in args else "detector"
    files = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] != "--name"]
    found = claim_step(args[0], [f for f in files if not f.endswith(".pdf")], next((f for f in files if f.endswith(".pdf")), None), name)
    print((Path(args[0]) / "claims.txt").read_text())
