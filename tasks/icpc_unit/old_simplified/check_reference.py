"""Check the reference geometry of task icpc_unit against hand-calculated values.

    python tasks/icpc_unit/reference/check_reference.py
"""

import math
from pathlib import Path

import build_reference as ref
from build_reference import icpc
import common
from common import CRYSTAL, WORLD

HERE = Path(__file__).parent
TOP, EDGE = 140.0, ref.WORLD / 2          # scan start, and the world boundary
PLATE, LMFE, FRAME = ("pen_plate", "PEN"), ("lmfe", "FusedSilica"), ("lmfe_frame", "Ultem")
HV_UP, HV_OUT = ("hv_up", "G4_KAPTON"), ("hv_out", "G4_KAPTON")


def cable(piece, i):
    return (f"signal_{piece}_{i}", "CoaxCable")
ROD_0, SUPPORT_1 = ("rod_0", "G4_Cu"), ("support_1", "PEN")   # rod at 0 deg, support at 180 deg


def down(x, y=0.0):
    return {"start": [x, y, TOP], "direction": [0, 0, -1]}


def inward(z, y=0.0):
    return {"start": [TOP, y, z], "direction": [-1, 0, 0]}


def sequence(*segments):
    """Segments as given, plus liquid argon up to the world boundary."""
    used = sum(length for _, length in segments)
    return [*segments, (WORLD, TOP + EDGE - used)]


above = TOP - icpc.HEIGHT                       # argon above the crystal
rod_top = ref.ROD_BOTTOM_Z + ref.ROD_L          # 118
clearance = ref.ROD_HOLE_R - ref.ROD_R          # 0.1
frame_wall = (ref.FRAME_T - ref.LMFE_T) / 2     # Ultem above and below the substrate
pitch_gap = ref.CABLE_XS[1] - ref.CABLE_XS[0] - 2 * ref.CABLE_R     # argon between neighbouring cables
bore_r_50 = icpc.BORE_R_BOTTOM + icpc.BORE_SLOPE * (50 - icpc.BORE_CONE_Z)
# where the line y = 20 crosses the straight edge that faces 60 degrees
side_x_20 = (ref.PLATE_SIDE_DIST - 20 * math.sin(math.radians(60))) / math.cos(math.radians(60))

CASES = [
    ("through the rod at 0 degrees", down(ref.ROD_POS_R),
     sequence((WORLD, TOP - rod_top), (ROD_0, ref.ROD_L))),
    ("x = 44: corner of the plate, outside the crystal", down(44),
     sequence((WORLD, TOP - ref.PLATE_TOP_Z), (PLATE, ref.PLATE_T))),
    ("support at 180 degrees: crystal, support, plate", down(-ref.SUPPORT_POS_R),
     sequence((WORLD, above), (CRYSTAL, icpc.HEIGHT), (SUPPORT_1, ref.GAP), (PLATE, ref.PLATE_T))),
    ("through the LMFE: crystal, gap, plate, frame, substrate, frame", down(0, ref.LMFE_CENTRE_Y),
     sequence((WORLD, above), (CRYSTAL, icpc.HEIGHT), (WORLD, ref.GAP), (PLATE, ref.PLATE_T),
              (FRAME, frame_wall), (LMFE, ref.LMFE_T), (FRAME, frame_wall))),
    ("through the HV cable under the plate: crystal, gap, plate, HV cable", down(0, 30),
     sequence((WORLD, above), (CRYSTAL, icpc.HEIGHT), (WORLD, ref.GAP), (PLATE, ref.PLATE_T),
              (HV_OUT, ref.HV_T))),
    ("down the upward HV cable", down(0, ref.HV_UP_Y),
     sequence((WORLD, TOP - ref.ROD_TOP_Z), (HV_UP, ref.HV_UP_L))),
    ("down one vertical signal cable", down(ref.CABLE_XS[2], ref.CABLE_UP_Y),
     sequence((WORLD, TOP - ref.ROD_TOP_Z), (cable("up", 2), ref.CABLE_UP_L))),
    ("across the four outward signal cables", {"start": [TOP, -33, ref.FRAME_CENTRE_Z], "direction": [-1, 0, 0]},
     sequence((WORLD, TOP - ref.CABLE_XS[3] - ref.CABLE_R),
              (cable("out", 3), 2 * ref.CABLE_R), (WORLD, pitch_gap),
              (cable("out", 2), 2 * ref.CABLE_R), (WORLD, pitch_gap),
              (cable("out", 1), 2 * ref.CABLE_R), (WORLD, pitch_gap),
              (cable("out", 0), 2 * ref.CABLE_R))),
    ("along y at z = 50: HV cable, crystal with borehole, between the signal cables",
     {"start": [0, TOP, 50], "direction": [0, -1, 0]},
     sequence((WORLD, TOP - ref.HV_UP_Y - ref.HV_T / 2), (HV_UP, ref.HV_T),
              (WORLD, ref.HV_UP_Y - ref.HV_T / 2 - icpc.RADIUS),
              (CRYSTAL, icpc.RADIUS - bore_r_50), (WORLD, 2 * bore_r_50),
              (CRYSTAL, icpc.RADIUS - bore_r_50))),
    ("axis: borehole, crystal, central hole of the plate", down(0),
     sequence((WORLD, TOP - 24.3), (CRYSTAL, 23.3))),
    ("z = -2.75: from a corner through a rod hole and the central hole to a straight edge", inward(-2.75),
     sequence((WORLD, TOP - ref.PLATE_R),
              (PLATE, ref.PLATE_R - ref.ROD_POS_R - ref.ROD_HOLE_R),
              (WORLD, clearance), (ROD_0, 2 * ref.ROD_R), (WORLD, clearance),
              (PLATE, ref.ROD_POS_R - ref.ROD_HOLE_R - ref.PLATE_HOLE_R),
              (WORLD, 2 * ref.PLATE_HOLE_R),
              (PLATE, ref.PLATE_SIDE_DIST - ref.PLATE_HOLE_R))),
    ("z = -2.75, y = 20: from the edge facing 60 degrees to the edge facing 180 degrees",
     inward(-2.75, 20),
     sequence((WORLD, TOP - side_x_20), (PLATE, side_x_20 + ref.PLATE_SIDE_DIST))),
    ("x = -33: beyond the edge facing 180 degrees, crystal only", down(-33),
     sequence((WORLD, above), (CRYSTAL, icpc.HEIGHT))),
    ("z = -1: between crystal and plate, through a rod and a support", inward(-1),
     sequence((WORLD, TOP - ref.ROD_POS_R - ref.ROD_R), (ROD_0, 2 * ref.ROD_R),
              (WORLD, ref.ROD_POS_R - ref.ROD_R + ref.SUPPORT_POS_R - ref.SUPPORT_R),
              (SUPPORT_1, 2 * ref.SUPPORT_R))),
]

if __name__ == "__main__":
    common.write(ref.build(), HERE / "reference.gdml")
    common.check(HERE / "reference.gdml", CASES, ref.masses_g(), HERE / "reference.png",
                 (-50, 50), (-20, 125), "Detector unit reference: cross-section at y = 0")
