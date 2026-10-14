"""Draw the part of G4GeoAgent that a run goes through today, from the PDF to the build plan.

    python diagrams/wired.py      writes diagrams/wired.png and .svg

What g4geoagent/pipeline.py runs as of 2026-10-14: evidence folder (step 1), the free readers (agent/statements.py),
Compare, the graph builder and geometry view (agent/detector_graph.py) and the Coordinator (agent/coordinator.py).
The boxes after the Coordinator are not wired to the graph yet; the run stops there.
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
    "off": ("#f2f2f2", "#b5b5b5", "#8a8a8a"),
}
GREY = "#777777"
fig, ax = plt.subplots(figsize=(14, 33))


def box(cx, cy, w, h, title, lines=(), kind="program", dashed=False):
    fill, edge, text = STYLE[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.14",
                                facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=2,
                                linestyle=(0, (4, 2)) if dashed else "-"))
    top = cy + h / 2 - 0.30
    ax.text(cx, top, title, ha="center", va="center", fontsize=12, color=text, zorder=3, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(cx, top - 0.36 - 0.30 * i, line, ha="center", va="center", fontsize=9.3, color=text, zorder=3)


def arrow(points, label=None, at=None, ha="left", dashed=False):
    xs, ys = zip(*points)
    style = (0, (4, 2)) if dashed else "-"
    ax.plot(xs[:-1], ys[:-1], color=GREY, linewidth=1.3, zorder=1, solid_capstyle="round", linestyle=style)
    ax.annotate("", xy=points[-1], xytext=points[-2], zorder=1,
                arrowprops={"arrowstyle": "->", "color": GREY, "linewidth": 1.3, "linestyle": style})
    if label:
        x, y = at if at else ((xs[-2] + xs[-1]) / 2 + 0.15, (ys[-2] + ys[-1]) / 2)
        ax.text(x, y, label, ha=ha, va="center", fontsize=9, color="#444444", zorder=3)


def band(y_top, y_bottom, label):
    ax.add_patch(FancyBboxPatch((-0.6, y_bottom), 15.0, y_top - y_bottom, boxstyle="round,pad=0,rounding_size=0.2",
                                facecolor="#f3f3ee", edgecolor="#d8d8d0", linewidth=1.0, zorder=0))
    ax.text(-0.35, y_top - 0.28, label, ha="left", va="center", fontsize=11, color="#555555", style="italic")


C, W = 5.4, 7.4          # main column
R = 12.1                 # side column

# ------------------------------------------------------------------ evidence folder
band(0.75, -4.3, "Evidence folder   (agent/evidence.py, step 1 in agent/documents.py)")
box(C, -0.1, W, 0.95, "Paper (PDF)", ["the starting document"], "data")
box(C, -1.75, W, 1.55, "Step 1: PDF to text and figures", ["tools: pymupdf, scipy; no model",
                                                           "letters repaired, preprint line numbers out,",
                                                           "captions and tables set apart, figures with their captions"])
arrow([(C, -0.58), (C, -0.97)])
box(3.3, -3.6, 4.0, 0.75, "Text", kind="data")
box(8.1, -3.6, 4.0, 0.75, "Figures", kind="data")
arrow([(3.6, -2.53), (3.4, -3.22)])
arrow([(7.2, -2.53), (7.9, -3.22)])

# ------------------------------------------------------------------ claims
band(-4.6, -15.0, "Readers and Compare: every construction fact as a plain sentence   (agent/statements.py)")
box(2.9, -5.95, 4.6, 1.85, "Reader A", ["model: lbl/gpt-oss-120b", "sections of about 6 pages, in parallel,",
                                        "each read twice"], "ai")
box(7.9, -5.95, 4.6, 1.85, "Reader B", ["model: lbl/gemma-4", "same sections, another way",
                                        "through the text, twice"], "ai")
arrow([(2.9, -3.98), (2.9, -5.02)])
arrow([(3.7, -3.98), (7.4, -5.02)])
ax.text(C, -7.15, "one sentence per fact + receipt: quote, numbers with units, parts, material, outer / inner, concluded?",
        ha="center", fontsize=9, color="#444444", style="italic")
box(C, -8.35, W, 1.55, "Compare: quote check and pooling", ["program: is the quote in the text? is each number in the quote?",
                                                            "the same fact from both readers is kept once"])
arrow([(2.9, -6.88), (4.2, -7.57)])
arrow([(7.9, -6.88), (6.6, -7.57)])
box(R, -8.35, 3.2, 1.0, "Dropped", ["quote or number not in the text"], "out")
arrow([(C + 3.7, -8.35), (R - 1.6, -8.35)])
box(C, -10.3, W, 1.55, "Cross-check by the other reader", ["for what only one reader has: right / wrong /",
                                                            "not construction / corrected (put right, checked again)"], "ai")
arrow([(C, -9.13), (C, -9.52)])
box(R, -10.3, 3.2, 1.0, "Disputed", ["rejected by the other reader"], "out")
arrow([(C + 3.7, -10.3), (R - 1.6, -10.3)])

box(R, -5.95, 3.6, 1.85, "Figure judge and reader", ["model: lbl/gemma-4 (vision)", "which figures show the build;",
                                                     "values of up to 3 per paper"], "ai")
arrow([(9.4, -3.98), (11.2, -5.02)])
arrow([(R, -6.88), (R, -7.3), (13.95, -7.3), (13.95, -12.1), (C + 3.7, -12.1)], "not cross-\nchecked", at=(14.05, -9.4))

box(C, -12.25, W, 1.25, "Compare: one claim per statement", ["program: id, sentence, page, who found it, every check"])
arrow([(C, -11.08), (C, -11.62)])
box(C, -14.1, W, 1.0, "Claims  (graph/claims.jsonl)", ["accepted, disputed and dropped, each with its reason"], "data")
arrow([(C, -12.88), (C, -13.6)])

# ------------------------------------------------------------------ graph builder
band(-15.3, -25.25, "Graph builder: a model builds, a program checks   (agent/detector_graph.py)")
box(C, -16.75, W, 1.85, "Parts and arrangement", ["model: lbl/gemma-4. Up to 220 claims: one call.",
                                                  "More: the tree first, then portions of 60 claims",
                                                  "in parallel: an edge, a note on a part, a new part, or set aside"], "ai")
arrow([(C, -14.6), (C, -15.82)])
box(R, -16.75, 3.4, 1.85, "Check", ["program: claims exist, one root,", "no loops, tree follows stated", "containment, every claim used"])
arrow([(C + 3.7, -16.5), (R - 1.7, -16.5)])
arrow([(R - 1.7, -17.0), (C + 3.7, -17.0)], "problems back,\nup to 3 times", at=(9.95, -17.5), ha="center")
box(C, -19.0, W, 1.25, "Values", ["model: lbl/gemma-4, 40 claims at a time, in parallel; checked the same way"], "ai")
arrow([(C, -17.68), (C, -18.37)])
box(C, -20.85, W, 1.55, "Finish", ["program: values once per part with their claim's number,",
                                   "stated containment as edges, what each part lacks"])
arrow([(C, -19.63), (C, -20.07)])
box(C, -22.75, W, 1.55, "Geometry view", ["model: sees the whole tree; each part keep, collapse",
                                          "into its container, or drop; a program checks"], "ai")
arrow([(C, -21.63), (C, -21.97)])
box(C, -24.5, W, 1.0, "Detector graph and geometry view", ["graph/detector_graph.json, graph/geometry_view.json"], "data")
arrow([(C, -23.53), (C, -24.0)])
box(R, -20.85, 3.4, 1.55, "Answer objections", ["model: changes or keeps each", "objected entry, from the claims;",
                                                "then Finish again"], "ai")
arrow([(R - 0.6, -21.63), (R - 0.6, -24.5), (C + 3.7, -24.5)], "changed graph", at=(R - 0.5, -23.0), dashed=True)

# ------------------------------------------------------------------ coordinator
band(-25.55, -31.2, "Coordinator: the build plan   (agent/coordinator.py)")
box(9.6, -26.95, 3.3, 1.55, "1. Teams", ["model: lbl/gemma-4", "cuts the kept tree;", "objects to graph entries"], "ai")
box(C + 0.6, -26.95, 3.4, 1.55, "2. Levels", ["model: lbl/gemma-4", "exact / simplified / lumped"], "ai")
box(2.3, -26.95, 3.9, 1.55, "3. Interfaces", ["model: lbl/gemma-4", "where teams meet:", "values or 'open'"], "ai")
arrow([(C, -25.0), (2.3, -26.17)])
arrow([(C, -25.0), (C + 0.6, -26.17)])
arrow([(C, -25.0), (9.6, -26.17)])
ax.text(C, -28.0, "each answer checked by a program and sent back with what fails", ha="center", fontsize=9, color="#444444", style="italic")
box(C, -28.95, W, 1.0, "Tasks", ["program: one task per kept part, with team, level, values, gaps"])
arrow([(C, -28.25), (C, -28.45)])
box(C, -30.55, W, 1.0, "Build plan  (build_plan.json, build_plan.txt)", ["teams, levels, interfaces, tasks, objections"], "data")
arrow([(C, -29.45), (C, -30.05)])
arrow([(11.25, -26.95), (R + 1.2, -26.95), (R + 1.2, -21.63)], "objections to\ngraph entries,\nonce", at=(R + 1.3, -24.3), dashed=True)
ax.text(R + 0.15, -29.0, "then the plan is\nmade once more on\nthe changed graph", ha="center", fontsize=9, color="#444444")

# ------------------------------------------------------------------ not wired
box(C, -32.4, W + 3.0, 1.25, "Teams, Research, Build, Measure, Look, Evaluator",
    ["exist from an earlier pass and still read the claims of the old readers; the run stops before them"], "off", dashed=True)
arrow([(C, -31.05), (C, -31.77)], dashed=True)

ax.legend(handles=[Patch(facecolor=STYLE[k][0], edgecolor=STYLE[k][1], label=n) for k, n in
                   (("ai", "Model call (free lbl/ models only)"), ("program", "Program or tool"), ("data", "Data"),
                    ("out", "Taken out, with the reason kept"), ("off", "Not wired yet"))],
          loc="lower center", bbox_to_anchor=(0.5, -0.012), ncol=3, frameon=False, fontsize=10.5)
ax.set_xlim(-0.9, 14.7)
ax.set_ylim(-34.0, 1.0)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("#fbfbf9")
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"wired.{suffix}", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote", HERE / "wired.png")
