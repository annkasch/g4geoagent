"""Check the reference geometry of task icpc_p43511a against hand-calculated values.

Builds reference.gdml, runs it through Geant4 and compares line scans and
the germanium mass with numbers worked out from the dimensions.

    python tasks/icpc_p43511a/reference/check_reference.py
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


# Heights and radii worked out by hand from the dimensions.
bore_bottom = ref.BORE_TUBE_Z - ref.BORE_R_BOTTOM                      # 24.3
edge_drop = ref.EDGE_R - math.sqrt(ref.EDGE_R**2 - 1.1**2)             # at r = 35.0
bore_r_60 = ref.BORE_R_BOTTOM + ref.BORE_SLOPE * (60 - ref.BORE_CONE_Z)
bore_r_27 = math.sqrt(ref.BORE_R_BOTTOM**2 - (ref.BORE_TUBE_Z - 27) ** 2)
edge_r_05 = ref.RADIUS - ref.EDGE_R + math.sqrt(ref.EDGE_R**2 - 1.5**2)   # outer radius at z = 0.5
dimple_r_05 = math.sqrt(ref.DIMPLE_R**2 - 0.5**2)
side = TOP - ref.RADIUS

CASES = [
    ("axis: borehole, then germanium down to the dimple", down(0),
     germanium(TOP - bore_bottom, bore_bottom - ref.DIMPLE_R)),
    ("x = 0.5: round borehole end and round dimple", down(0.5),
     germanium(TOP - (ref.BORE_TUBE_Z - math.sqrt(25 - 0.25)),
               ref.BORE_TUBE_Z - math.sqrt(25 - 0.25) - math.sqrt(1 - 0.25))),
    ("x = 3: round borehole end, flat bottom", down(3),
     germanium(TOP - (ref.BORE_TUBE_Z - 4), ref.BORE_TUBE_Z - 4)),
    ("x = 14.5: beside the borehole, ends in the groove", down(14.5),
     germanium(TOP - ref.HEIGHT, ref.HEIGHT - ref.GROOVE_DEPTH)),
    ("x = 35: through both rounded edges", down(35),
     germanium(TOP - ref.HEIGHT + edge_drop, ref.HEIGHT - 2 * edge_drop)),
    ("z = 60: across the tapered borehole", inward(60),
     germanium(side, ref.RADIUS - bore_r_60, 2 * bore_r_60, ref.RADIUS - bore_r_60)),
    ("z = 39: across the straight borehole", inward(39),
     germanium(side, ref.RADIUS - 5, 10, ref.RADIUS - 5)),
    ("z = 27: across the round borehole end", inward(27),
     germanium(side, ref.RADIUS - bore_r_27, 2 * bore_r_27, ref.RADIUS - bore_r_27)),
    ("z = 0.5: across rounded edge, groove and dimple", inward(0.5),
     germanium(TOP - edge_r_05, edge_r_05 - 16, 3, 13 - dimple_r_05, 2 * dimple_r_05,
               13 - dimple_r_05, 3, edge_r_05 - 16)),
]

if __name__ == "__main__":
    common.write(ref.build(), HERE / "reference.gdml")
    mass = ref.analytic_volume() / 1000 * common.GE_DENSITY
    common.check(HERE / "reference.gdml", CASES, {"crystal": mass}, HERE / "reference.png",
                 (-45, 45), (-10, 110), "P43511A reference: cross-section at y = 0")
