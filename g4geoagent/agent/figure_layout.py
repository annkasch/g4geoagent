"""The coarse layout of a detector from a figure: its main parts, their outer shape, and what is inside what.

    python -m g4geoagent.agent.figure_layout <figure> [<figure> ...] --out <folder>

A vision model describes the figure into a fixed form; a program checks the form (unique ids, every 'inside' names a
part, no loops). Parts keep the figure's label when there is one; unlabelled parts get a description. Nothing is
matched to a paper here: this is the figure alone.
"""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from g4geoagent.agent import detector_graph as D
from g4geoagent.reviewer.look import _image

MODEL = "lbl/gemma-4"
SHAPES = ("cylinder", "tube", "cup", "vessel", "box", "sphere", "plate", "ring", "array", "other")


class Panel(BaseModel):
    panel: str = Field(description="where in the figure: left, middle, right, inset ...")
    view: Literal["cutaway", "cross_section", "outside_view", "photo", "schematic", "plot", "other"]
    shows: str = Field(description="what it shows, and how it relates to the other panels (a zoom of a part, ...)")


class Part(BaseModel):
    id: str = Field(description="short id: p1, p2, ...")
    label: str = Field(default="", description="the label the figure gives it, copied exactly; '' if none")
    description: str = Field(description="what it looks like: colour, form, where it is")
    shape: Literal["cylinder", "tube", "cup", "vessel", "box", "sphere", "plate", "ring", "array", "other"] = Field(
        description="its outer form: cylinder (solid), tube (open at both ends), cup (closed at one end), vessel (closed, "
                    "with a cavity), box, sphere, plate (flat: a plane, disk or slab), ring, array (many equal items), other")
    hollow: bool = Field(description="true if it has a cavity that holds other parts or a filling")
    inside: str = Field(description="the id of the part it is directly inside, or 'none'")
    where: str = Field(default="", description="where in that part: top, bottom, centre, around the wall, ...")
    count: str = Field(default="", description="for an array: how many items, if the figure shows or says it")
    panel: str = Field(default="", description="the panel it is seen in")
    profile: str = Field(default="", description="its outline: ends (flat, domed, conical, open), a neck, a flange, steps")
    box: list[float] = Field(default_factory=list, description="where it is in the image: [left, right, top, bottom] as "
                                                               "fractions of the image width and height, 0 to 1")


class Layout(BaseModel):
    panels: list[Panel]
    axis: str = Field(description="the detector's main axis and symmetry: 'vertical, round about its axis', 'long box', ...")
    parts: list[Part]
    order: str = Field(default="", description="the order of the main parts from outside to inside, or top to bottom")


PROMPT = """This figure shows a particle detector, or part of one. Describe its layout for someone who will build a \
simplified 3D model of it. Only the figure counts: do not add parts you know from elsewhere.

1. panels: what each panel of the figure is (cutaway, cross-section, outside view, photo, ...) and how the panels \
relate (one is a zoom of a part of another).
2. parts: the main parts, from the outside in. Main parts are vessels, tanks, shells, shields, frames, large \
supports, the sensitive volume, arrays of sensors or detectors, plates and planes. Not screws, cables or small \
fittings. For each part:
   - label: the label the figure gives it, copied exactly ('' if it has none);
   - description: what it looks like and where it is;
   - shape: its outer form;
   - hollow: whether it holds other parts or a filling;
   - inside: the part it is directly inside ('none' for the outermost); a part shown only in a zoom panel is inside \
the part it is a zoom of;
   - where in that part it sits (top, bottom, centre, around the wall);
   - count, for an array, if the figure shows or says it;
   - profile: its outline, as a builder needs it: the shape of its top and bottom ends (flat, domed, conical, open), a \
neck, a flange, steps in its width. Leave box empty.
3. axis: the main axis and the symmetry. order: outside to inside, or top to bottom.

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def check(layout):
    """What is wrong with a layout, as sentences for the model."""
    problems = []
    ids = [p.id for p in layout.parts]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"the id {dup} is used twice")
    known = set(ids)
    for p in layout.parts:
        if p.inside != "none" and p.inside not in known:
            problems.append(f"part {p.id}: it is inside '{p.inside}', which is not a part id")
        if p.inside == p.id:
            problems.append(f"part {p.id}: it cannot be inside itself")
    inside = {p.id: p.inside for p in layout.parts}
    for start in ids:
        seen, at = set(), start
        while at in inside and at not in seen:
            seen.add(at)
            at = inside[at]
        if at in seen:
            problems.append(f"'inside' runs in a loop through {', '.join(sorted(seen))}")
            break
    if layout.parts and all(p.inside != "none" for p in layout.parts):
        problems.append("no part is outermost (inside 'none')")
    return problems


def box_problems(layout):
    """Boxes that are missing, malformed, or outside the box of the part they are inside."""
    problems = []
    by_id = {p.id: p for p in layout.parts}
    for p in layout.parts:
        b = p.box
        if len(b) != 4 or not all(0 <= x <= 1 for x in b) or b[0] >= b[1] or b[2] >= b[3]:
            problems.append(f"part {p.id}: box must be [left, right, top, bottom] with 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
            continue
        outer = by_id.get(p.inside)
        if outer and len(outer.box) == 4 and p.panel == outer.panel:
            o = outer.box
            if b[0] < o[0] - 0.02 or b[1] > o[1] + 0.02 or b[2] < o[2] - 0.02 or b[3] > o[3] + 0.02:
                problems.append(f"part {p.id}: its box {b} is not within the box of {outer.id} {o}, which it is inside")
    return problems


def sketch(layout, figure, path):
    """The layout drawn as boxes over a faded copy of the figure, and the plain figure beside it."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image
    im = Image.open(figure).convert("RGB")
    w, h = im.size
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 7 * h / w + 0.6))
    a.imshow(im, alpha=0.25)
    colours = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#bcbd22"]
    depth = {}
    by_id = {p.id: p for p in layout.parts}
    for p in layout.parts:
        d, at = 0, p.inside
        while at in by_id and d < 10:
            d, at = d + 1, by_id[at].inside
        depth[p.id] = d
    for i, p in enumerate(sorted(layout.parts, key=lambda q: depth[q.id])):
        if len(p.box) != 4:
            continue
        x0, x1, y0, y1 = p.box
        c = colours[i % len(colours)]
        a.add_patch(Rectangle((x0 * w, y0 * h), (x1 - x0) * w, (y1 - y0) * h, fill=False, ec=c, lw=2))
        a.text(x0 * w + 3, y0 * h + 12, f"{p.id} {p.label or p.description[:22]}", color=c, fontsize=8, fontweight="bold")
    a.set_title("Your layout: each part's box over the faded figure", fontsize=10); a.axis("off")
    b.imshow(im); b.set_title("The figure", fontsize=10); b.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=90); plt.close(fig)


COMPARE = """Left: your layout of this figure, each part's box drawn over a faded copy of the figure. Right: the figure. \
Compare them part by part: does each box cover exactly its part (not more, not less)? Are parts missing (look at \
small devices on walls, arrays, plates, necks)? Are the boxes of parts inside another part within its box? Are \
the shapes, profiles and what is inside what right?
Send the complete corrected layout as one JSON object in the same form. If nothing needs to change, send it unchanged."""


def read_with_sketches(figure, out, caption="", log=None, model=MODEL, rounds=3):
    """Read, draw, compare and correct, up to `rounds` times. Returns (Layout, list of sketch paths)."""
    request = PROMPT.format(schema=json.dumps(Layout.model_json_schema(), separators=(",", ":")))
    if caption:
        request = f"The figure's caption: \"{caption}\"\n\n" + request
    view = _larger(figure)
    messages = [{"role": "user", "content": [{"type": "text", "text": request}, _image(view)]}]
    full = lambda l: check(l) + box_problems(l)
    layout, _ = D._with_repairs(model, messages, Layout, full, log, "figure_layout")
    drawn = []
    for number in range(rounds):
        path = Path(out) / f"{Path(figure).stem}_sketch{number}.png"
        sketch(layout, view, path)
        drawn.append(path)
        if number == rounds - 1:
            break
        for m in messages[1:]:
            if m["role"] == "user" and isinstance(m["content"], list):
                m["content"] = [c for c in m["content"] if c.get("type") == "text"]
        messages += [{"role": "assistant", "content": layout.model_dump_json()},
                     {"role": "user", "content": [{"type": "text", "text": COMPARE}, _image(path)]}]
        new, _ = D._with_repairs(model, messages, Layout, full, log, "figure_layout_compare")
        if new.model_dump() == layout.model_dump():
            break
        layout = new
    return layout, drawn


def snap(layout, figure, margin=0.04):
    """Move each box edge to the strongest edge of the image within `margin` of it (fraction of the image).
    Returns {part id: (old box, new box)}."""
    import numpy as np
    from PIL import Image
    g = np.asarray(Image.open(figure).convert("L"), dtype=float)
    h, w = g.shape
    gx = np.abs(np.diff(g, axis=1)); gy = np.abs(np.diff(g, axis=0))
    moved = {}
    for p in layout.parts:
        if len(p.box) != 4:
            continue
        x0, x1, y0, y1 = p.box
        rows = slice(int(y0 * h), max(int(y1 * h), int(y0 * h) + 1))
        cols = slice(int(x0 * w), max(int(x1 * w), int(x0 * w) + 1))
        col_strength = gx[rows, :].sum(axis=0)          # vertical edges, summed over the part's rows
        row_strength = gy[:, cols].sum(axis=1)          # horizontal edges, summed over the part's columns

        def best(strength, at, n):
            lo, hi = max(0, int((at - margin) * n)), min(len(strength), int((at + margin) * n) + 1)
            return (lo + int(np.argmax(strength[lo:hi]))) / n if hi > lo else at
        new = [best(col_strength, x0, w), best(col_strength, x1, w), best(row_strength, y0, h), best(row_strength, y1, h)]
        moved[p.id] = (list(p.box), [round(x, 3) for x in new])
    return moved


def _larger(path, longest=1600):
    """The figure as PNG, enlarged so that its longer side is about `longest` pixels (thin walls stay visible)."""
    from PIL import Image
    path = Path(path)
    out = path.with_name(path.stem + "_view.png")
    im = Image.open(path).convert("RGB")
    factor = max(1.0, longest / max(im.size))
    im.resize((int(im.width * factor), int(im.height * factor)), Image.LANCZOS).save(out)
    return out


def read_layout(figure, caption="", log=None, model=MODEL):
    """The layout of one figure. Returns (Layout, rounds of problems)."""
    request = PROMPT.format(schema=json.dumps(Layout.model_json_schema(), separators=(",", ":")))
    if caption:
        request = f"The figure's caption: \"{caption}\"\n\n" + request
    content = [{"type": "text", "text": request}, _image(_larger(figure))]
    return D._with_repairs(model, [{"role": "user", "content": content}], Layout, check, log, "figure_layout")


def as_text(layout):
    lines = [f"axis: {layout.axis}", f"order: {layout.order}"]
    lines += [f"panel {p.panel}: {p.view} - {p.shows}" for p in layout.panels]
    children = {}
    for p in layout.parts:
        children.setdefault(p.inside, []).append(p)

    def walk(parent, depth):
        for p in children.get(parent, []):
            lines.append(f"{'  ' * depth}{p.id} {('[' + p.label + '] ') if p.label else ''}{p.shape}{', hollow' if p.hollow else ''}"
                         f"{', at ' + p.where if p.where else ''}{', x' + p.count if p.count else ''}: {p.description}")
            walk(p.id, depth + 1)
    walk("none", 0)
    return "\n".join(lines)


if __name__ == "__main__":
    from g4geoagent.agent.runlog import RunLog
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    for figure in [a for i, a in enumerate(args) if a != "--out" and (i == 0 or args[i - 1] != "--out")]:
        layout, rounds = read_layout(figure, log=RunLog(out / "log.jsonl"))
        (out / f"{Path(figure).stem}.json").write_text(layout.model_dump_json(indent=1))
        (out / f"{Path(figure).stem}.txt").write_text(as_text(layout) + "\n")
        print(f"== {Path(figure).name} (problems per round: {[len(r) for r in rounds]})\n{as_text(layout)}\n")


# ------------------------------------------------------------------ names from the text, and sizes from one stated size

class Match(BaseModel):
    figure_part: str
    paper_part: str = Field(description="the paper's name for it, from the list, or 'not in the paper'")
    confidence: Literal["high", "medium", "low"]
    why: str


class Matches(BaseModel):
    matches: list[Match]


MATCH_PROMPT = """A figure of the detector {detector} has been described part by part, without the paper. Match each \
figure part to the part of the paper that it shows, using the paper's statements below: what the part is, what it is \
inside, its sizes and its proportions. The figure parts have no reliable names; judge by place, shape, nesting and \
size. Sizes help: the box of a figure part is given as fractions of the image (left, right, top, bottom; the image is \
{w} x {h} pixels), so the ratio of two widths in the figure should be close to the ratio of the stated diameters. If \
no part of the paper fits, say 'not in the paper'. Two figure parts never match the same paper part.

FIGURE PARTS:
{figure}

THE PAPER'S PARTS AND WHAT IT STATES ABOUT THEM:
{paper}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def paper_parts(claims):
    """{part name: [statements]} of the accepted claims, by the parts each claim names."""
    out = {}
    for c in claims:
        if c.status != "accepted" or not c.statement:
            continue
        for name in c.parts or [c.subject]:
            out.setdefault(name, []).append(c.statement)
    return out


def match_names(layout, claims, detector, image_size, log=None, model="lbl/gpt-oss-120b"):
    parts = paper_parts(claims)
    figure = "\n".join(f"  {p.id}: {p.description}; {p.shape}{', hollow' if p.hollow else ''}; inside {p.inside}"
                       f"{', at ' + p.where if p.where else ''}; profile: {p.profile or '-'}; box {[round(x, 2) for x in p.box]}"
                       for p in layout.parts)
    paper = "\n".join(f"  {name}: " + " | ".join(s[:160] for s in said[:6]) for name, said in parts.items())
    request = MATCH_PROMPT.format(detector=detector, w=image_size[0], h=image_size[1], figure=figure, paper=paper,
                                  schema=json.dumps(Matches.model_json_schema(), separators=(",", ":")))

    def problems(a):
        out = [f"'{m.paper_part}' is not one of the paper's parts" for m in a.matches
               if m.paper_part != "not in the paper" and m.paper_part not in parts]
        named = [m.paper_part for m in a.matches if m.paper_part != "not in the paper"]
        out += [f"'{n}' is matched twice" for n in sorted({n for n in named if named.count(n) > 1})]
        out += [f"no match for figure part {p.id}" for p in layout.parts if p.id not in {m.figure_part for m in a.matches}]
        return out
    return D._with_repairs(model, [{"role": "user", "content": request}], Matches, problems, log, "figure_match")


def stated_sizes(claims, part):
    """Widths (diameters) and heights in mm that accepted claims state for a part: {'width': [...], 'height': [...]}."""
    import re
    unit = {"mm": 1, "cm": 10, "m": 1000}
    out = {"width": [], "height": []}
    for c in claims:
        if c.status != "accepted" or c.kind != "value" or part not in (c.parts or [c.subject]):
            continue
        text = c.statement.lower()
        for number, u, what in re.findall(r"(\d+(?:\.\d+)?)\s*(mm|cm|m)\b[\s-]*(diameter|height|high|wide|tall)?", text):
            mm = float(number) * unit[u]
            if what in ("diameter", "wide") or (not what and "diameter" in text and "height" not in text):
                out["width"].append(mm)
            elif what in ("height", "high", "tall"):
                out["height"].append(mm)
    return out


def scaled(layout, matches, claims, image_size):
    """Every figure part's width, height and centre height in metres, scaled by the largest matched part (high
    confidence) whose width the paper states. Returns (reference, [rows])."""
    w, h = image_size
    by = {m.figure_part: m for m in matches}
    candidates = []
    for p in layout.parts:
        m = by.get(p.id)
        if m and m.confidence == "high" and m.paper_part != "not in the paper" and len(p.box) == 4:
            sizes = stated_sizes(claims, m.paper_part)
            if sizes["width"]:
                candidates.append(((p.box[1] - p.box[0]) * w, p, m.paper_part, max(sizes["width"])))
    if not candidates:
        return None, []
    px, ref, name, mm = max(candidates, key=lambda c: c[0])
    per_px = mm / px
    rows = []
    for p in layout.parts:
        if len(p.box) != 4:
            continue
        m = by.get(p.id)
        paper = m.paper_part if m else ""
        sizes = stated_sizes(claims, paper) if paper and paper != "not in the paper" else {"width": [], "height": []}
        rows.append({"part": p.id, "paper": paper, "confidence": m.confidence if m else "",
                     "width_m": round((p.box[1] - p.box[0]) * w * per_px / 1000, 2),
                     "height_m": round((p.box[3] - p.box[2]) * h * per_px / 1000, 2),
                     "centre_x_m": round(((p.box[0] + p.box[1]) / 2 - (ref.box[0] + ref.box[1]) / 2) * w * per_px / 1000, 2),
                     "centre_z_m": round(((ref.box[2] + ref.box[3]) / 2 - (p.box[2] + p.box[3]) / 2) * h * per_px / 1000, 2),
                     "stated_width_m": [round(x / 1000, 3) for x in sizes["width"]],
                     "stated_height_m": [round(x / 1000, 3) for x in sizes["height"]]})
    return {"part": ref.id, "paper": name, "width_m": mm / 1000}, rows


def coarse_picture(rows, figure, path, title=""):
    """The scaled layout as nested rectangles in metres (a cut through the axis), next to the figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 6))
    colours = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]
    for i, r in enumerate(sorted(rows, key=lambda r: -r["width_m"] * r["height_m"])):
        c = colours[i % len(colours)]
        x0, z0 = r["centre_x_m"] - r["width_m"] / 2, r["centre_z_m"] - r["height_m"] / 2
        a.add_patch(Rectangle((x0, z0), r["width_m"], r["height_m"], fill=False, ec=c, lw=2))
        a.text(x0 + 0.05, z0 + r["height_m"] - 0.3, f"{r['part']} {r['paper'] or ''}\n{r['width_m']} x {r['height_m']} m", color=c, fontsize=8)
    a.autoscale_view(); a.set_aspect("equal"); a.set_xlabel("x (m)"); a.set_ylabel("z (m)"); a.set_title(title or "Coarse layout, scaled", fontsize=10)
    b.imshow(Image.open(figure)); b.axis("off"); b.set_title("The figure", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=90); plt.close(fig)


# ------------------------------------------------------------------ the figure's description corrected by the text

class Field_(BaseModel):
    value: str
    source: Literal["figure", "text", "both"]


class Reconciled(BaseModel):
    figure_part: str = Field(description="the figure part's id, or 'text only' for a part the text names that the figure does not show")
    paper_part: str = Field(description="the paper's name, or 'not in the paper'")
    what: Field_ = Field(description="what the part is (from the text where it says)")
    shape: Field_ = Field(description="outer form and outline: ends, neck, flange, steps")
    inside: str = Field(description="the paper's name (or figure id) of the part it is directly inside, or 'none'")
    inside_source: Literal["figure", "text", "both"]
    arrangement: str = Field(default="", description="where in that part, and for arrays how the items are arranged")
    material: Field_ | None = None


class Question(BaseModel):
    about: str = Field(description="the figure part id (or paper part) the question is about")
    question: str = Field(description="what to look at in the figure, asked so that the picture can answer it")


class Reconciliation(BaseModel):
    parts: list[Reconciled]
    conflicts: list[str] = Field(default_factory=list, description="where figure and text disagree, and what was taken")
    questions: list[Question] = Field(default_factory=list, description="for the figure reader: doubts the picture can settle")


RECONCILE_PROMPT = """A figure of the detector {detector} was described part by part without the paper. Correct that \
description with the paper's statements. The text has more weight than the figure:
- match each figure part to the paper's part it shows; judge by place, nesting and shape, not by the figure reader's \
words, which can be wrong (it may call a water tank a vacuum vessel);
- names, what a part is, materials, and what is inside what come from the text wherever it states them;
- shapes, outlines (ends, neck, flange) and arrangements stay as the figure shows them, unless the text says otherwise;
- for each field say where it comes from: figure, text, or both (they agree);
- parts the text names that the figure does not show: add them with figure_part 'text only' when they are main parts;
- list every disagreement under conflicts, with what you took;
- shape is the outline only (ends, neck, flange, panels, steps), never sizes from the text;
- questions: whenever a match or a shape is uncertain, or figure and text disagree in a way the picture could settle, \
ask the figure reader about what can be SEEN: is it one piece or several? is there another part between these two? \
what does this neck connect to? are there small devices on this wall, how many, how arranged? does this part touch \
that one? The figure reader has not read the paper: never ask what a part is or which paper part it is (it cannot \
tell); work that out yourself from its answers. Ask nothing you can settle from the text.
{dialogue}
FIGURE DESCRIPTION:
{figure}

WHAT IS INSIDE WHAT, AS THE PAPER STATES IT:
{containment}

THE PAPER'S PARTS AND ITS STATEMENTS ABOUT THEM:
{paper}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def stated_containment(claims):
    """(outer, inner, statement) for every accepted claim that states one part inside another."""
    out = []
    for c in claims:
        if c.status == "accepted" and c.relation == "contains" and c.subject and c.object:
            out.append((c.subject, c.object, c.statement or c.line()))
        elif c.status == "accepted" and getattr(c, "outer", "") and getattr(c, "inner", ""):
            out.append((c.outer, c.inner, c.statement))
    return out


def reconcile_check(answer, layout, claims):
    problems = []
    names = paper_parts(claims)
    import re as _re
    for q in answer.questions:
        text = q.question.lower()
        named = [n for n in names if len(n) > 3 and n.replace("_", " ") in text.replace("_", " ")]
        if named or _re.search(r"\b(represent|correspond|is it the|is this the|which (part|component)|identify)\b", text):
            problems.append(f"question about {q.about} asks what a part is ('{q.question[:90]}'); the figure reader has not read "
                            "the paper: ask about what can be seen instead")
    figure_ids = {p.id for p in layout.parts}
    mapped = [r.figure_part for r in answer.parts if r.figure_part != "text only"]
    problems += [f"figure part {p} is not in the result" for p in sorted(figure_ids - set(mapped))]
    problems += [f"figure part {p} appears twice" for p in sorted({p for p in mapped if mapped.count(p) > 1})]
    paper = [r.paper_part for r in answer.parts if r.paper_part != "not in the paper"]
    problems += [f"'{p}' is not one of the paper's parts" for p in sorted(set(paper) - set(names))]
    problems += [f"paper part '{p}' appears twice" for p in sorted({p for p in paper if paper.count(p) > 1})]
    inside = {r.paper_part: r.inside for r in answer.parts if r.paper_part != "not in the paper"}
    figure_of = {r.paper_part: r.figure_part for r in answer.parts}

    def within(a, b):
        seen, at = set(), inside.get(a)
        while at and at != "none" and at not in seen:
            if at == b:
                return True
            seen.add(at)
            at = inside.get(at)
        return False
    # the figure's own nesting is kept unless the text states otherwise
    key = {r.figure_part: (r.paper_part if r.paper_part != "not in the paper" else r.figure_part) for r in answer.parts}
    inside.update({r.figure_part: r.inside for r in answer.parts if r.paper_part == "not in the paper"})
    stated = {(o, i) for o, i, _ in stated_containment(claims)}
    for part in layout.parts:
        if part.inside in key and part.id in key:
            child, parent = key[part.id], key[part.inside]
            if not within(child, parent) and not any(i == child for _, i in stated):
                problems.append(f"the figure shows {part.id} ({child}) inside {part.inside} ({parent}), and the text does not say "
                                f"otherwise, but the result does not put {child} inside {parent}")
    for outer, inner, statement in stated_containment(claims):
        if outer in inside and inner in inside and not within(inner, outer):
            problems.append(f"the paper states that {inner} is inside {outer} (\"{statement[:120]}\"), but the result does not put it there")
        elif inner in inside and outer not in inside:
            problems.append(f"the paper states that {inner} is inside {outer} (\"{statement[:120]}\"), but {outer} is not in the result; "
                            f"match it to the figure part around {figure_of.get(inner, inner)}, or add it as 'text only'")
    return problems


def reconcile(layout, claims, detector, log=None, model="lbl/gpt-oss-120b", dialogue=""):
    figure = as_text(layout)
    containment = "\n".join(f"  {o} contains {i}: \"{s[:140]}\"" for o, i, s in stated_containment(claims)) or "  (none stated)"
    paper = "\n".join(f"  {name}: " + " | ".join(s[:160] for s in said[:6]) for name, said in paper_parts(claims).items())
    request = RECONCILE_PROMPT.format(detector=detector, figure=figure, containment=containment, paper=paper, dialogue=dialogue,
                                      schema=json.dumps(Reconciliation.model_json_schema(), separators=(",", ":")))
    return D._with_repairs(model, [{"role": "user", "content": request}], Reconciliation,
                           lambda a: reconcile_check(a, layout, claims), log, "figure_reconcile")


def reconciled_text(answer):
    lines = []
    children = {}
    key = {r.figure_part: (r.paper_part if r.paper_part != "not in the paper" else r.figure_part) for r in answer.parts
           if r.figure_part != "text only"}
    for r in answer.parts:                       # 'inside' may name a figure id or a paper part: use one key
        children.setdefault(key.get(r.inside, r.inside), []).append(r)
    names = {r.paper_part for r in answer.parts} | set(key)

    def walk(parent, depth, seen):
        for r in children.get(parent, []):
            key = r.paper_part if r.paper_part != "not in the paper" else r.figure_part
            if key in seen:
                continue
            mat = f"; material {r.material.value} [{r.material.source}]" if r.material else ""
            lines.append(f"{'  ' * depth}{r.paper_part} ({r.figure_part}): {r.what.value} [{r.what.source}]; "
                         f"shape: {r.shape.value} [{r.shape.source}]; inside [{r.inside_source}]"
                         f"{'; ' + r.arrangement if r.arrangement else ''}{mat}")
            walk(key, depth + 1, seen | {key})
    roots = [r for r in answer.parts if r.inside == "none" or r.inside not in names]
    children.pop("none", None)
    for r in roots:
        children.setdefault("__root__", []).append(r)
    walk("__root__", 0, set())
    lines += [f"CONFLICT: {c}" for c in answer.conflicts]
    return "\n".join(lines)


# ------------------------------------------------------------------ the figure reader answers; the step as a whole

class Answer(BaseModel):
    question: int = Field(description="the number of the question")
    answer: str = Field(description="what the figure shows, as seen; 'cannot tell' if the picture does not show it")


class Answers(BaseModel):
    answers: list[Answer]
    corrected_parts: list[Part] = Field(default_factory=list, description="parts of your layout you correct, with the same id")
    new_parts: list[Part] = Field(default_factory=list, description="parts you missed, with new ids")


ANSWER_PROMPT = """You described this figure of a particle detector earlier:
{layout}

Someone who has read the paper asks you about the figure. Look at the figure again, carefully, at the places the \
questions point to, and answer each from what you see, not from what the paper might say. Then correct the parts of \
your description that were wrong (same id) and add parts you missed (new ids). Leave box empty.

Questions:
{questions}

Answer with one JSON object that fits this schema and nothing else:
{schema}"""


def answer_questions(figure, layout, questions, log=None, model=MODEL):
    """The figure reader looks again and answers. Returns (Answers, the layout with its corrections)."""
    listing = "\n".join(f"  {i + 1}. ({q.about}) {q.question}" for i, q in enumerate(questions))
    request = ANSWER_PROMPT.format(layout=as_text(layout), questions=listing,
                                   schema=json.dumps(Answers.model_json_schema(), separators=(",", ":")))
    content = [{"type": "text", "text": request}, _image(_larger(figure))]

    def updated(a):
        parts = {p.id: p for p in layout.parts}
        parts.update({p.id: p for p in a.corrected_parts})
        parts.update({p.id: p for p in a.new_parts})
        return layout.model_copy(update={"parts": list(parts.values())})
    answers, _ = D._with_repairs(model, [{"role": "user", "content": content}], Answers, lambda a: check(updated(a)), log,
                                 "figure_answers")
    return answers, updated(answers)


def layout_step(figure, claims, detector, out, log=None, rounds=3, caption=""):
    """The layout of a detector from a figure, corrected by the text, with up to `rounds` rounds of questions from the
    text side to the figure reader. Writes into `out`: figure_layout.json (the figure alone), layout.json and
    layout.txt (the result), dialogue.json. Returns the Reconciliation. `claims`: the agreed claims (claims.Claim)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    layout, _ = read_layout(figure, caption, log)
    (out / "figure_layout.json").write_text(layout.model_dump_json(indent=1))
    history, asked = [], set()
    for number in range(rounds + 1):
        dialogue = ""
        if history:
            dialogue = "\nEARLIER QUESTIONS TO THE FIGURE READER AND ITS ANSWERS (the description above includes its corrections):\n" + \
                "\n".join(f"  Q: {h['question']}\n  A: {h['answer']}" for h in history) + "\n"
        result, _ = reconcile(layout, claims, detector, log, dialogue=dialogue)
        new = [q for q in result.questions if q.question.strip().lower() not in asked]
        if not new or number == rounds:
            break
        answers, layout = answer_questions(figure, layout, new, log)
        for i, q in enumerate(new):
            asked.add(q.question.strip().lower())
            a = next((x.answer for x in answers.answers if x.question == i + 1), "no answer")
            history.append({"round": number + 1, "about": q.about, "question": q.question, "answer": a})
    (out / "layout.json").write_text(result.model_dump_json(indent=1))
    (out / "layout.txt").write_text(reconciled_text(result) + "\n")
    (out / "dialogue.json").write_text(json.dumps(history, indent=1))
    (out / "figure_layout_final.json").write_text(layout.model_dump_json(indent=1))
    return result
