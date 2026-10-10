"""Evaluator: grade a finished build against the public geometry code of the experiment.

Runs after the run and outside it. It is the only part that reads GitHub. The
public code is the closest ground truth there is, and far more detailed than a
build from papers can be, so the grader reasons about what is worth comparing:

1. it looks at the list of files of the repository and picks the ones that define the geometry,
2. it reads them and writes down the main parts, each with the line of code that shows it,
3. a program checks that every quoted line exists,
4. it compares those parts with the built geometry, as Geant4 reports it, and says for each
   difference whether it matters at the level of detail that documents allow.

Nothing of this goes back into the run.
"""

import json
import re
from pathlib import Path

import requests
from pydantic import BaseModel, Field

from g4geoagent.agent.compare import _squash
from g4geoagent.agent.llm import call_llm_json

MODEL = "lbl/gpt-oss-120b"
SOURCE = (".py", ".cc", ".cpp", ".cxx", ".hh", ".h", ".icc", ".gdml", ".xml", ".yaml", ".yml", ".json", ".mac", ".txt")
MAX_FILES, MAX_WORDS = 8, 5000


class Files(BaseModel):
    files: list[str] = Field(description="Paths of the files that define the detector geometry, most important first")
    reason: str


class ReferencePart(BaseModel):
    part: str = Field(description="What the part is, in plain words")
    shape: str = Field(description="Its shape as the code builds it, e.g. 'cylinder with domed ends', 'box', 'tube'")
    dimensions: str = Field(description="Main dimensions with units, as the code gives them. Empty if they are loaded from elsewhere")
    material: str = ""
    inside: str = Field(default="", description="What it is placed in")
    count: str = Field(default="", description="How many, if the code shows it")
    quote: str = Field(description="One line of the code, copied exactly, that shows this part")


class ReferenceParts(BaseModel):
    parts: list[ReferencePart]


class Difference(BaseModel):
    part: str
    kind: str = Field(description="One of: agrees, missing, extra, wrong_place, wrong_shape, wrong_size, wrong_count, "
                                  "wrong_material, beyond_expected_detail, cannot_tell")
    build: str = Field(description="What the build has, in one sentence")
    reference: str = Field(description="What the public code has, in one sentence")
    matters: str = Field(description="high, medium or low: how much this matters for a geometry built from documents")
    why: str = Field(description="One sentence of reasoning")


class Differences(BaseModel):
    differences: list[Difference]


def list_repository(repository):
    """[(path, size)] of the source files of a GitHub repository."""
    response = requests.get(f"https://api.github.com/repos/{repository}/git/trees/HEAD", params={"recursive": 1}, timeout=60)
    response.raise_for_status()
    return [(e["path"], e.get("size", 0)) for e in response.json()["tree"]
            if e["type"] == "blob" and e["path"].endswith(SOURCE) and 200 < e.get("size", 0) < 400_000]


def fetch_file(repository, path):
    response = requests.get(f"https://raw.githubusercontent.com/{repository}/HEAD/{path}", timeout=60)
    response.raise_for_status()
    return response.text


def built_parts(report):
    """The built geometry as a table of text: each kind of part once, with count, material, size and mother."""
    kinds = {}
    for part in report.get("parts", [])[1:]:
        kind = re.sub(r"[_\-]?\d+(_\d+)*$", "", part["volume"])
        entry = kinds.setdefault(kind, {"count": 0, **part})
        entry["count"] += 1
    return "\n".join(f"  {entry['count']} x {kind}: {entry['solid']}, {entry['material']}, "
                     f"size {' x '.join(f'{s:.0f}' for s in entry.get('size_mm', []))} mm, "
                     f"in {re.sub(r'[_-]?[0-9]+(_[0-9]+)*$', '', str(entry['mother']))}" for kind, entry in kinds.items())


def grade(detector, repository, build, plan, folder, log=None, model=MODEL):
    """Grade `build` (the best build of a run). Returns {"files", "reference", "dropped", "findings", "error"}."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result = {"files": [], "reference": [], "dropped": 0, "findings": [], "error": ""}
    try:
        listing = list_repository(repository)
    except Exception as error:
        return {**result, "error": f"could not list {repository}: {type(error).__name__}: {str(error)[:200]}"}
    shown = "\n".join(f"  {path} ({size} bytes)" for path, size in listing[:600])
    request = (f"This is the list of files of the public simulation code of the detector {detector} ({repository}).\n"
               f"{shown}\n\nWe want to know how the code builds the detector geometry: the main vessels, shields, "
               f"the sensitive detectors and how they are arranged. Pick up to {MAX_FILES} files that define this, the "
               "ones for the large structures and for the arrangement first. Leave out tests, documentation and "
               "optical or physics settings. Answer with one JSON object: {\"files\": [paths], \"reason\": \"one sentence\"}")
    try:
        chosen, _ = call_llm_json(model, [{"role": "user", "content": request}], Files, log=log,
                                  stage="evaluator_files", temperature=0)
    except ValueError:
        return {**result, "error": "the model did not pick files"}
    known = {path for path, _ in listing}
    texts = {}
    for path in [f for f in chosen.files if f in known][:MAX_FILES]:
        try:
            texts[path] = fetch_file(repository, path)
            (folder / path.replace("/", "__")).write_text(texts[path])
        except Exception:
            continue
    result["files"] = list(texts)

    for path, text in texts.items():
        words = text.split(" ")
        excerpt = " ".join(words[:MAX_WORDS])
        request = (f"This file is from the public simulation code of the detector {detector}: {path}\n\n"
                   f"```\n{excerpt}\n```\n\nList the parts of the detector that this file builds or places: vessels, "
                   "shields, structures, sensitive detectors, repeated units. For each: its shape, its main "
                   "dimensions as the code gives them, its material, what it is placed in, how many there are, and "
                   "one line of the code, copied exactly, that shows the part. At most 15 parts, the large and the "
                   "sensitive ones first. If the file builds no parts, give an empty list. Answer with one JSON "
                   "object that fits this schema and nothing else:\n"
                   + json.dumps(ReferenceParts.model_json_schema(), separators=(",", ":")))
        try:
            answer, _ = call_llm_json(model, [{"role": "user", "content": request}], ReferenceParts, log=log,
                                      stage="evaluator_read", temperature=0)
        except ValueError:
            continue
        squashed = _squash(text)
        for part in answer.parts:               # a part counts only if its line of code exists
            if part.quote.strip() and _squash(part.quote) in squashed:
                result["reference"].append({"file": path, **part.model_dump()})
            else:
                result["dropped"] += 1
    if not result["reference"]:
        return {**result, "error": "no part of the public code could be read with a verified line of code"}

    reference = "\n".join(f"  {p['part']}: {p['shape']}; {p['dimensions']}; {p['material']}; in {p['inside']}; "
                          f"count {p['count']}  [{p['file']}: {p['quote'].strip()[:90]}]" for p in result["reference"])
    levels = "\n".join(f"  {p.name}: {p.detail}, {p.form}, inside {p.inside}" for p in plan.parts) if plan else ""
    request = (f"You grade a geometry model of the detector {detector}. It was built by a program from papers only. "
               "The public simulation code of the experiment is the closest ground truth, but it is far more detailed "
               "than a build from papers can or needs to be.\n\n"
               f"Parts of the public code (with the line that shows each):\n{reference}\n\n"
               f"The built geometry, as Geant4 reports it (count x kind: solid, material, size, mother):\n{built_parts(build['report'])}\n\n"
               + (f"The detail level the build aimed at for each part:\n{levels}\n\n" if levels else "") +
               "Reason about what is worth comparing, then compare. Go through the parts of the public code from the "
               "largest structures to the sensitive detectors. For each, find its counterpart in the build by what it "
               "is, not by its name, and say how the two differ: missing, wrong_place, wrong_shape, wrong_size, "
               "wrong_count, wrong_material, or agrees. Fine detail of the code that no paper would give is "
               "beyond_expected_detail and does not count against the build. Parts of the build with no counterpart "
               "are extra. If the list above does not let you decide, say cannot_tell. Compare numbers only where "
               "both sides give them. Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Differences.model_json_schema(), separators=(",", ":")))
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": request}], Differences, log=log,
                                  stage="evaluator_compare", temperature=0)
        result["findings"] = [d.model_dump() for d in answer.differences]
    except ValueError:
        result["error"] = "the model gave no usable comparison"
    (folder / "grade.json").write_text(json.dumps(result, indent=1))
    return result


def grade_report(detector, repository, result):
    lines = [f"# Evaluation: {detector} against {repository}", "",
             "Written after the run, outside the system. Nothing of it went back into the run.", ""]
    if result["error"]:
        lines += [f"**Problem:** {result['error']}", ""]
    lines += [f"Files of the public code that were read: {', '.join('`' + f + '`' for f in result['files']) or 'none'}.",
              f"Parts found in them with a verified line of code: {len(result['reference'])}. "
              f"Parts dropped because the quoted line does not exist: {result['dropped']}.", ""]
    counts = {}
    for finding in result["findings"]:
        counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1
    if counts:
        lines += ["## Summary", "", "| Kind | Number |", "|---|---|"] + [f"| {k} | {n} |" for k, n in sorted(counts.items())] + [""]
        lines += ["## Differences", "", "| Part | Kind | Matters | Build | Public code | Reasoning |", "|---|---|---|---|---|---|"]
        clean = lambda text: " ".join(str(text).split()).replace("|", "/")
        order = {"high": 0, "medium": 1, "low": 2}
        for f in sorted(result["findings"], key=lambda f: order.get(f["matters"], 3)):
            lines.append(f"| {clean(f['part'])} | {f['kind']} | {f['matters']} | {clean(f['build'])} | "
                         f"{clean(f['reference'])} | {clean(f['why'])} |")
        lines.append("")
    lines += ["## Parts read from the public code", ""]
    lines += [f"- **{p['part']}** ({p['shape']}; {p['dimensions'] or 'dimensions not in this file'}; {p['material']}) "
              f"`{p['file']}`: `{p['quote'].strip()[:120]}`" for p in result["reference"]]
    return "\n".join(lines) + "\n"
