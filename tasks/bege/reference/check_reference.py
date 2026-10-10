"""Check the reference geometry of task bege against hand-calculated values.

    python tasks/bege/reference/check_reference.py
"""

import math
from pathlib import Path

import build_reference as ref
import common
from common import CRYSTAL, WORLD

HERE = Path(__file__).parent
TOP, EDGE = 140.0, ref.WORLD / 2          # scan start, and the world boundary


def down(x):
    return {"start": [x, 0, TOP], "direction": [0, 0, -1]}


def inward(z):
    return {"start": [TOP, 0, z], "direction": [-1, 0, 0]}


def germanium(*lengths):
    """Liquid argon and germanium alternate, starting in argon, up to the world boundary."""
    return common.alternate(WORLD, CRYSTAL, lengths, TOP + EDGE)


# Worked out by hand from the dimensions.
edge_drop = ref.EDGE_R - math.sqrt(ref.EDGE_R**2 - 1.1**2)               # at r = 35.0
edge_r_1 = ref.RADIUS - ref.EDGE_R + math.sqrt(ref.EDGE_R**2 - 1.0**2)   # outer radius at z = 1

CASES = [
    ("axis: full height", down(0), germanium(TOP - ref.HEIGHT, ref.HEIGHT)),
    ("x = 8.5: ends in the groove", down(8.5),
     germanium(TOP - ref.HEIGHT, ref.HEIGHT - ref.GROOVE_DEPTH)),
    ("x = 35: through both rounded edges", down(35),
     germanium(TOP - ref.HEIGHT + edge_drop, ref.HEIGHT - 2 * edge_drop)),
    ("z = 20: full diameter", inward(20), germanium(TOP - ref.RADIUS, 2 * ref.RADIUS)),
    ("z = 1: across rounded edge and groove", inward(1),
     germanium(TOP - edge_r_1, edge_r_1 - 10, 3, 14, 3, edge_r_1 - 10)),
]

if __name__ == "__main__":
    common.write(ref.build(), HERE / "reference.gdml")
    mass = ref.analytic_volume() / 1000 * common.GE_DENSITY
    common.check(HERE / "reference.gdml", CASES, {"crystal": mass}, HERE / "reference.png",
                 (-45, 45), (-10, 50), "BEGe reference: cross-section at y = 0")
