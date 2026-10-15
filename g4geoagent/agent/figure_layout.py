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
neck, a flange, steps in its width;
   - box: the rectangle it occupies in the image, [left, right, top, bottom] as fractions of the image width and \
height (0 = left or top edge, 1 = right or bottom edge). Be careful: the boxes of parts inside another part lie \
within its box, and the proportions between parts matter.
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
