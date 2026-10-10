"""Look: compare pictures of the built geometry with figures of the real detector.

The figures come from the PDFs in the evidence folder: the starting paper and
whatever Research saved. A vision model first says which figures show how the
detector is built, then compares the build with each of them and lists what is
arranged or shaped differently. Only gross differences are asked for: the free
models misread dimensions, but they do see what is inside what.
"""

import base64
import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from g4geoagent.agent.llm import call_llm_json

MODEL = "lbl/gemma-4"
MIN_SIZE = (250, 200)        # pixels: smaller images are logos and symbols
MAX_FIGURES = 3


class FigureKind(BaseModel):
    shows_construction: bool = Field(description="true for a drawing, rendering or photo that shows how the detector "
                                                 "or a part of it is built; false for plots of data and diagrams of logic")
    shows: str = Field(description="One sentence: what is seen, and which parts are labelled")


class Finding(BaseModel):
    part: str = Field(description="The part concerned, by the name used in the list of built parts where there is one")
    issue: str = Field(description="What is arranged or shaped differently in the build, in one sentence")
    fix: str = Field(description="What the build should do instead, in one sentence")


class Findings(BaseModel):
    findings: list[Finding]


def _image(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def extract_figures(pdf_path, folder):
    """Save the figures of a PDF as PNG files. Returns [{file, page, caption, source}]."""
    import pymupdf
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    figures = []
    with pymupdf.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            captions = re.findall(r"(Fig(?:ure|\.)\s*\d+[.:][^\n]*(?:\n[^\n]+){0,5})", page.get_text())
            large = [i for i in page.get_image_info() if i["width"] >= MIN_SIZE[0] and i["height"] >= MIN_SIZE[1]]
            for k, info in enumerate(large):
                name = f"{Path(pdf_path).stem}_p{number}_{k}.png"
                page.get_pixmap(clip=pymupdf.Rect(info["bbox"]), dpi=150).save(folder / name)
                caption = " ".join(captions[min(k, len(captions) - 1)].split()) if captions else ""
                figures.append({"file": name, "page": number, "caption": caption[:500], "source": Path(pdf_path).name})
    return figures


def construction_figures(figures, folder, detector, log=None, model=MODEL, most=MAX_FIGURES):
    """The figures that show how the detector is built, each with a sentence on what it shows."""
    kept = []
    for figure in figures:
        request = (f"This figure is from a paper about the detector {detector}. Its caption: \"{figure['caption']}\".\n"
                   "Does it show how the detector or a part of it is built? Answer with one JSON object: "
                   '{"shows_construction": true or false, "shows": "one sentence"}')
        try:
            answer, _ = call_llm_json(model, [{"role": "user", "content": [{"type": "text", "text": request},
                                                                           _image(Path(folder) / figure["file"])]}],
                                      FigureKind, log=log, stage="look_figures", temperature=0)
        except ValueError:
            continue
        if log:
            log.event("figure", "look", file=figure["file"], construction=answer.shows_construction, shows=answer.shows)
        if answer.shows_construction:
            kept.append({**figure, "shows": answer.shows})
    return kept[:most]


def compare(renders, figure, folder, detector, built_parts, log=None, model=MODEL):
    """What is arranged or shaped differently in the build than in one figure. Returns a list of Finding."""
    request = (f"The first {len(renders)} pictures show a geometry model of the detector {detector} that a program "
               "built: 3D views with the front half cut away, from the whole detector inwards. The last picture is a "
               f"figure of the real detector from a paper. Its caption: \"{figure['caption']}\".\n\n"
               "Parts of the built model, with what each one sits in:\n" + built_parts + "\n\n"
               "Compare the build with the figure, part by part, from the outside in. List what is arranged or shaped "
               "differently in the build: a part that sits in the wrong place or in the wrong part, a part that is "
               "solid where the figure shows it hollow or open, a shape that is clearly different (flat or domed, one "
               "piece or many), a part of the figure that the build lacks. Leave out colours, materials, viewing "
               "angle, and anything about exact sizes. Leave out what you cannot see in the figure. "
               "Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Findings.model_json_schema(), separators=(",", ":")))
    content = [{"type": "text", "text": request}, *(_image(r) for r in renders), _image(Path(folder) / figure["file"])]
    try:
        answer, _ = call_llm_json(model, [{"role": "user", "content": content}], Findings, log=log,
                                  stage="look_compare", temperature=0)
    except ValueError:
        return []
    return answer.findings


def as_feedback(findings_by_figure):
    """The findings as text for the builder."""
    lines = []
    for figure, findings in findings_by_figure:
        if findings:
            lines.append(f"Against the figure \"{figure['caption'][:150]}\":")
            lines += [f"- {f.part}: {f.issue} {f.fix}" for f in findings]
    return "\n".join(lines)
