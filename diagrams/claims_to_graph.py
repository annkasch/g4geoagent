"""Draw the part of G4GeoAgent from the paper to the detector graph, with every program step and tool.

    python diagrams/claims_to_graph.py      writes diagrams/claims_to_graph.png and .svg

This is a close-up of the boxes Evidence folder, Readers, Compare, Agreed claims, Graph builder and
Detector graph of diagrams/architecture.png. It shows what the code in g4geoagent/agent/claims.py and
g4geoagent/agent/detector_graph.py does, step by step.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch

HERE = Path(__file__).parent
STYLE = {   # kind: (fill, edge, text)
    "ai": ("#ecebfb", "#7a6fd0", "#2f2a7a"),
    "program": ("#e1f3ec", "#3f9c7c", "#0f5a43"),
    "data": ("#ffffff", "#bdbdbd", "#111111"),
    "out": ("#fdf1e3", "#d39a4a", "#7a4a0f"),
}
GREY = "#777777"
fig, ax = plt.subplots(figsize=(13.5, 27))


def box(cx, cy, w, h, title, lines=(), kind="program", dashed=False):
    fill, edge, text = STYLE[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.14",
                                facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=2,
                                linestyle=(0, (4, 2)) if dashed else "-"))
    top = cy + h / 2 - 0.30
    ax.text(cx, top, title, ha="center", va="center", fontsize=12, color=text, zorder=3, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(cx, top - 0.36 - 0.30 * i, line, ha="center", va="center", fontsize=9.3, color=text, zorder=3)


def arrow(points, label=None, at=None, ha="left"):
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color=GREY, linewidth=1.3, zorder=1, solid_capstyle="round")
    ax.annotate("", xy=points[-1], xytext=points[-2], zorder=1,
                arrowprops={"arrowstyle": "->", "color": GREY, "linewidth": 1.3})
    if label:
        x, y = at if at else ((xs[-2] + xs[-1]) / 2 + 0.15, (ys[-2] + ys[-1]) / 2)
        ax.text(x, y, label, ha=ha, va="center", fontsize=9, color="#444444", zorder=3)


def band(y_top, y_bottom, label, at_bottom=False):
    ax.add_patch(FancyBboxPatch((-0.6, y_bottom), 14.6, y_top - y_bottom, boxstyle="round,pad=0,rounding_size=0.2",
                                facecolor="#f3f3ee", edgecolor="#d8d8d0", linewidth=1.0, zorder=0))
    ax.text(-0.35, y_bottom + 0.3 if at_bottom else y_top - 0.28, label, ha="left", va="center", fontsize=11,
            color="#555555", style="italic")


C, W = 6.0, 6.4          # main column
R = 11.9                 # side column: what is taken out, and tools

# ------------------------------------------------------------------ documents
band(0.75, -3.95, "Documents")
box(C, 0, W, 0.95, "Paper (PDF)", ["the starting document; later also papers found by Research"], "data")
box(3.6, -1.75, 4.6, 1.25, "PDF to text", ["tool: pymupdf; damaged letters repaired,", "captions and tables set apart"])
box(8.6, -1.75, 4.6, 1.25, "Cut out figures", ["tool: pymupdf; stored and drawn figures,", "all panels, each with its caption"])
arrow([(4.6, -0.48), (3.9, -1.12)])
arrow([(7.4, -0.48), (8.3, -1.12)])
box(3.6, -3.25, 4.6, 0.75, "Text of the paper", kind="data")
box(8.6, -3.25, 4.6, 0.75, "Figures", kind="data")
arrow([(3.6, -2.38), (3.6, -2.87)])
arrow([(8.6, -2.38), (8.6, -2.87)])

# ------------------------------------------------------------------ claim step
band(-4.25, -17.95, "Claim step: every fact the documents state, one claim per fact   (g4geoagent/agent/claims.py)", True)
box(2.6, -5.5, 4.4, 1.6, "Reader A", ["model: lbl/gpt-oss-120b", "reads the text twice", "parts, values, relations, with quotes"], "ai")
box(7.3, -5.5, 4.4, 1.6, "Reader B", ["model: lbl/gemma-4", "reads the text twice", "another way through the text"], "ai")
arrow([(3.2, -3.63), (2.8, -4.7)])
arrow([(4.4, -3.63), (6.9, -4.7)])
box(C - 1.05, -7.5, 8.2, 1.25, "Pool the two passes of each reader", ["program: the same record is kept once"])
arrow([(2.6, -6.3), (2.6, -6.87)])
arrow([(7.3, -6.3), (7.3, -6.87)])
box(C - 1.05, -9.35, 8.2, 1.85, "Quote check",
    ["program: is the quote in the text? is the number in the quote?", "reference marks such as [8] are ignored",
     "a quote that fails is cut to its longest part that is in the text"])
arrow([(C - 1.05, -8.13), (C - 1.05, -8.42)])
box(R, -9.35, 3.2, 1.0, "Dropped", ["quote not in the text"], "out")
arrow([(C + 3.05, -9.35), (R - 1.6, -9.35)])

box(C - 1.05, -11.5, 8.2, 1.85, "Find numbers that were left out",
    ["program: every number of a sentence the readers used, digits and", "number words, that no value from that same sentence covers",
     "Reader A decides for each: a construction value? (then quote check)"], "program")
ax.text(C + 2.85, -10.75, "+ model", ha="right", fontsize=8.5, color=STYLE["ai"][2])
arrow([(C - 1.05, -10.28), (C - 1.05, -10.57)])
box(C - 1.05, -13.75, 8.2, 2.15, "Cross-check",
    ["program: which records does only one reader have?", "the other reader checks each against its sentence, twice:",
     "confirmed / corrected (kind of relation) / wrong / not construction", "taken out only if rejected both times"], "ai")
arrow([(C - 1.05, -12.43), (C - 1.05, -12.67)])
box(R, -13.75, 3.2, 1.0, "Disputed", ["rejected by the other reader"], "out")
arrow([(C + 3.05, -13.75), (R - 1.6, -13.75)])

box(R, -5.5, 3.6, 1.6, "Figure judge", ["model: lbl/gemma-4 (vision)", "does the figure show", "the construction?"], "ai")
box(R, -7.5, 3.6, 1.25, "Figure reader", ["model: lbl/gemma-4 (vision)", "labels, shapes, what is in what"], "ai")
arrow([(10.2, -3.63), (11.4, -4.7)])
arrow([(R, -6.3), (R, -6.87)])
arrow([(R + 1.55, -8.13), (R + 1.75, -8.6), (R + 1.75, -15.85), (C + 3.05, -15.85)],
      "not\ncross-\nchecked", at=(R + 1.85, -11.6))

box(C - 1.05, -16.05, 8.2, 1.85, "Write the claims",
    ["program: one claim per fact: part, value, shape, feature or relation",
     "the same fact under two names for the part becomes one claim",
     "each gets an id, its sentence and page, who found it, every check"])
arrow([(C - 1.05, -14.83), (C - 1.05, -15.12)])
arrow([(R, -9.85), (R, -10.3), (R - 2.2, -10.3), (R - 2.2, -16.4), (C + 3.05, -16.4)], "kept, marked", at=(R - 2.1, -12.2))
arrow([(R, -14.25), (R, -16.6), (C + 3.05, -16.6)])

# ------------------------------------------------------------------ data between the steps
box(C - 1.05, -18.6, 8.2, 0.95, "Claims  (claims.jsonl)", ["accepted, disputed and dropped, each with its reason"], "data")
arrow([(C - 1.05, -16.98), (C - 1.05, -18.12)])

# ------------------------------------------------------------------ graph step
band(-19.3, -30.05, "Graph step: a model builds the graph, a program checks its work   (g4geoagent/agent/detector_graph.py)", True)
box(3.3, -20.75, 6.0, 1.85, "Build the structure", ["model: lbl/gpt-oss-120b", "from the part, shape, feature and relation claims:",
                                                  "which names are one part, what is inside what, edges"], "ai")
arrow([(C - 1.05, -19.08), (3.9, -19.82)])
box(10.4, -20.75, 6.6, 2.5, "Check the structure",
    ["program:", "every entry names claims, and they exist", "one root, no loops, every container is a part",
     "the tree follows relations that claims state", "every claim is used, or set aside for a fixed reason",
     "an inferred relation carries its reasoning"])
arrow([(6.3, -20.45), (7.1, -20.45)])
arrow([(7.1, -21.05), (6.3, -21.05)], "problems back,\nup to 3 times", at=(6.72, -21.55), ha="center")

box(3.3, -23.9, 6.0, 1.85, "Add the values", ["model: lbl/gpt-oss-120b", "from the value claims, 40 at a time, in parallel:",
                                              "which part each value belongs to"], "ai")
arrow([(3.3, -21.68), (3.3, -22.97)])
box(10.4, -23.9, 6.6, 2.2, "Check the values",
    ["program:", "a number in the graph is the number of its claim,", "unless marked as derived, with reasoning",
     "a construction value is never set aside as 'not geometry'", "every value claim is used or set aside"])
arrow([(6.3, -23.6), (7.1, -23.6)])
arrow([(7.1, -24.2), (6.3, -24.2)], "problems back,\nup to 3 times", at=(6.72, -24.7), ha="center")

box(C - 1.05, -27.35, 8.2, 3.1, "Finish the graph",
    ["program:", "takes out what the checks still reject", "keeps each value once per part, with the wording and unit of its claim",
     "copies shapes and features from the cited claims", "adds an edge for every claim that says where a part is",
     "puts back a stated value where only a derived one was kept (*)", "lists what each part still lacks: shape, sizes, material, place"])
arrow([(3.3, -24.83), (3.9, -25.8)])
box(R, -27.35, 3.2, 1.3, "Taken out,\nunaccounted", [], "out")
arrow([(C + 3.05, -27.35), (R - 1.6, -27.35)])

box(C - 1.05, -31.05, 8.2, 1.25, "Detector graph  (detector_graph.json)",
    ["parts as a tree, values, relations, unknowns; every entry names its claims"], "data")
arrow([(C - 1.05, -28.9), (C - 1.05, -30.42)])

ax.text(-0.35, -32.35, "(*) written, not yet tested on the papers. Not shown: Research, which will add claims from further documents "
        "through the same claim step.", fontsize=9.5, color="#444444", va="center")
ax.legend(handles=[Patch(facecolor=STYLE[k][0], edgecolor=STYLE[k][1], label=n) for k, n in
                   (("ai", "Model call"), ("program", "Program (deterministic) or tool"), ("data", "Data"), ("out", "Taken out, with the reason kept"))],
          loc="lower center", bbox_to_anchor=(0.5, -0.012), ncol=4, frameon=False, fontsize=10.5)
ax.set_xlim(-0.9, 14.3)
ax.set_ylim(-33.3, 1.0)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("#fbfbf9")
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"claims_to_graph.{suffix}", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote", HERE / "claims_to_graph.png")
