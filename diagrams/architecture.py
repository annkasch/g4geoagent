"""Draw the G4GeoAgent architecture diagram.

    python diagrams/architecture.py      writes diagrams/architecture.png and .svg
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
    "data": ("#ffffff", "#cfcfcf", "#111111"),
}
GREY = "#777777"
fig, ax = plt.subplots(figsize=(11.5, 23))


def box(cx, cy, w, h, title, sub=None, kind="ai"):
    fill, edge, text = STYLE[kind]
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.14",
                                facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=2))
    ax.text(cx, cy + (0.17 if sub else 0), title, ha="center", va="center", fontsize=12.5,
            color=text, zorder=3)
    if sub:
        ax.text(cx, cy - 0.2, sub, ha="center", va="center", fontsize=10, color=text, zorder=3)


def arrow(points, label=None, at=None, ha="left", both=False):
    """Line through `points` with an arrow head at the end."""
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color=GREY, linewidth=1.3, zorder=1, solid_capstyle="round")
    ax.annotate("", xy=points[-1], xytext=points[-2], zorder=1,
                arrowprops={"arrowstyle": "<->" if both else "->", "color": GREY, "linewidth": 1.3})
    if label:
        x, y = at if at else ((xs[-2] + xs[-1]) / 2 + 0.15, (ys[-2] + ys[-1]) / 2)
        ax.text(x, y, label, ha=ha, va="center", fontsize=9.5, color="#444444", zorder=3)


C, W, H = 6.0, 6.0, 0.9          # main column: centre, width, box height
L1, L2, R1 = 0.2, 1.9, 10.6      # x of the loops on the left and right
RX = 12.6                        # x of Research and of its line up to the evidence folder

# --- evidence and reading
box(C, 0, W, H, "Evidence folder", "Documents and figures + saved finds", "data")
box(4.4, -1.5, 2.8, H, "Reader A")
box(7.6, -1.5, 2.8, H, "Reader B")
arrow([(4.4, -0.45), (4.4, -1.05)])
arrow([(7.6, -0.45), (7.6, -1.05)])
box(C, -3.0, W, H, "Compare", "Match claims, coverage check", "program")
arrow([(4.4, -1.95), (4.4, -2.55)])
arrow([(7.6, -1.95), (7.6, -2.55)])
arrow([(3.0, -3.0), (L2, -3.0), (L2, -1.5), (3.0, -1.5)], "disagree:\nre-read", at=(L2 - 0.12, -2.25), ha="right")
box(C, -4.5, W, H, "Agreed claims", "Each with source and uncertainty", "data")
arrow([(C, -3.45), (C, -4.05)], "agree")

# --- coordination and building
box(C, -6.0, W, H, "Coordinator", "Splits detector, detail levels, interfaces")
arrow([(C, -4.95), (C, -5.55)])
arrow([(9.0, -5.8), (R1, -5.8), (R1, -3.0), (9.0, -3.0)], "re-check\nclaim", at=(R1 + 0.12, -4.4))
for x, name in ((3.6, "Team 1"), (5.6, "Team 2"), (9.0, "Team N")):
    box(x, -7.7, 1.7, 0.8, name)
    arrow([(x, -6.9), (x, -7.3)], both=True) if x != 5.6 else None
ax.plot([3.6, 9.0], [-6.9, -6.9], color=GREY, linewidth=1.3, zorder=1)
arrow([(C, -6.9), (C, -6.45)])
arrow([(5.6, -6.9), (5.6, -7.3)], both=True)
ax.text(7.3, -7.7, "...", ha="center", va="center", fontsize=14)
ax.text(3.2, -6.7, "questions, changes", ha="left", fontsize=9.5, color="#444444")
ax.text(6.2, -6.7, "interfaces, answers", ha="left", fontsize=9.5, color="#444444")

ax.add_patch(FancyBboxPatch((2.7, -10.75), 6.6, 2.15, boxstyle="round,pad=0,rounding_size=0.2",
                            facecolor="none", edgecolor="#bbbbbb", linestyle=(0, (4, 3)), linewidth=1.1))
ax.plot([C, C], [-8.1, -8.6], color=GREY, linewidth=1.1, linestyle=(0, (2, 3)))
ax.text(C + 0.15, -8.35, "each team runs", fontsize=9.5, color="#444444", va="center")
ax.text(2.9, -8.85, "Piece loop", fontsize=10, color="#444444", va="center")
box(3.9, -9.55, 1.7, H, "Build", "Code")
box(6.0, -9.55, 1.7, H, "Measure", "vs claims", "program")
box(8.1, -9.55, 1.7, H, "Look", "vs pictures")
arrow([(4.75, -9.55), (5.15, -9.55)])
arrow([(6.85, -9.55), (7.25, -9.55)])
arrow([(8.1, -10.0), (8.1, -10.4), (3.9, -10.4), (3.9, -10.0)], "fail: fix", at=(C, -10.58), ha="center")
ax.plot([6.0, 6.0], [-10.0, -10.4], color=GREY, linewidth=1.3, zorder=1)

# --- research, inside each team
box(RX, -9.55, 3.6, H, "Research", "Online: text and figures")
arrow([(9.3, -9.55), (RX - 1.8, -9.55)], "when a value or\na part is missing", at=(RX, -10.4), ha="center")
arrow([(RX, -9.1), (RX, 0.0), (9.0, 0.0)], "saves pages\nand figures", at=(RX + 0.12, -3.4))

# --- whole-detector checks
rows = [(-11.9, "Integrate", "Place subsystems at interfaces", "program"),
        (-13.3, "Check whole detector", "Overlaps, mass, counts", "program"),
        (-14.7, "Run in Geant4", "Load, overlaps, geantinos, cross-sections", "program"),
        (-16.1, "Final look", "Against the original pictures, by region", "ai"),
        (-17.6, "Did this round change anything?", "Checks, Reviewer findings, new evidence", "program")]
previous = -10.75
for y, title, sub, kind in rows:
    arrow([(C, previous), (C, y + H / 2)])
    box(C, y, W, H, title, sub, kind)
    previous = y - H / 2
for y in (-13.3, -14.7, -16.1):
    ax.plot([3.0, L2], [y, y], color=GREY, linewidth=1.3, zorder=1)
ax.plot([L2, L2], [-16.1, -13.3], color=GREY, linewidth=1.3, zorder=1)
arrow([(L2, -13.3), (L2, -7.7), (2.75, -7.7)], "subsystem\nerror:\nowning team", at=(L2 - 0.12, -11.0), ha="right")
arrow([(L2, -14.7), (L1, -14.7), (L1, -6.0), (3.0, -6.0)], "interface\nor claim", at=(L1 - 0.1, -8.6), ha="right")
arrow([(9.0, -17.6), (R1, -17.6), (R1, -7.7), (9.85, -7.7)], "yes:\nnext round", at=(R1 + 0.12, -12.6))
box(C, -19.1, W, H, "GDML + evidence report + run log", "The run ends here, by its own rule", "data")
arrow([(C, -18.05), (C, -18.65)], "no: stop")

# --- outside the system
ax.plot([-1.4, 13.9], [-20.05, -20.05], color="#999999", linewidth=1.2, linestyle=(0, (6, 4)))
ax.text(-1.4, -20.3, "Afterwards, outside the system. Only for detectors with a public implementation.",
        fontsize=10, color="#444444", va="center", style="italic")
box(1.6, -21.4, 2.9, H, "Public code", "Closest ground truth", "data")
box(7.3, -21.4, 7.2, H, "Evaluator", "Reasons about what to compare, measures with tools")
arrow([(3.05, -21.4), (3.7, -21.4)])
arrow([(C, -19.55), (C, -20.95)])
box(C, -22.9, W, H, "System audit", "Patterns across runs and detector types", "program")
arrow([(C, -21.85), (C, -22.45)])
box(C, -24.4, W, H, "Design changes", "Architecture, tools, lessons. Never back into a run", "data")
arrow([(C, -23.35), (C, -23.95)])

ax.legend(handles=[Patch(facecolor=STYLE[k][0], edgecolor=STYLE[k][1], label=n)
                   for k, n in (("ai", "AI step"), ("program", "Program"), ("data", "Data"))],
          loc="lower center", bbox_to_anchor=(0.5, -0.005), ncol=3, frameon=False, fontsize=11)
ax.set_xlim(-1.7, 14.9)
ax.set_ylim(-25.7, 0.7)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("#fbfbf9")
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"architecture.{suffix}", dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
print("wrote", HERE / "architecture.png")
