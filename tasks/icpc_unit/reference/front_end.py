"""Front-end parts of the icpc_unit reference: clamps, LMFE, pins, washers, springs, cables.

Dimensions and positions follow legend-pygeom-l200 (hpge_strings.py). The
signal side is +y, the HV side is -y. "Outward" means away from the crystal axis.
"""

import math

import pyg4ometry.geant4 as g4

import build_reference as ref
import common
from common import TWO_PI

GAP = 0.001                           # between the pieces of one cable
SIGNAL_CABLE_Y0 = ref.SIGNAL_R + 7.5 / 2 + 0.1        # origin of the signal cable: 18.1
HV_CABLE_Y0 = ref.HV_R - 3                            # origin of the HV cable: 34.5
SIGNAL_PINS = [(x, ref.SIGNAL_R + 0.25) for x in (-5.05, 5.05)]
HV_PINS = [(x, -(ref.HV_R - 3.45)) for x in (-4.0, 4.0)]

# Placement rotations. Parts are defined with local x pointing outward.
SIGNAL_SIDE = ref.rotation(local_x=(0, 1, 0), local_y=(-1, 0, 0))
HV_SIDE = ref.rotation(local_x=(0, -1, 0), local_y=(1, 0, 0))
# Cable bends are tubes: the tube axis lies along x, and the arc runs from
# "straight down" to "outward" as seen from the tube axis.
SIGNAL_BEND = ref.rotation(local_x=(0, 1, 0), local_y=(0, 0, 1))
HV_BEND = ref.rotation(local_x=(0, -1, 0), local_y=(0, 0, 1))


def signal_clamp_solid(reg):
    """Ultem clamp of the LMFE: a block with two long bars that run outward beside the LMFE."""
    mid = g4.solid.Box("signal_clamp_mid", 7.5, 9.5, ref.T_CLAMP, reg)
    bar = g4.solid.Box("signal_clamp_bar", 27, 3, ref.T_CLAMP, reg)
    solid = mid
    for i, sign in enumerate((1, -1)):
        solid = g4.solid.Union(f"signal_clamp_u{i}", solid, bar,
                               [[0, 0, 0], [(27 - 7.5) / 2, sign * (9.5 + 3) / 2, 0]], reg)
    hole = g4.solid.Tubs("signal_clamp_hole", 0, 1.5, ref.T_CLAMP + 1, 0, TWO_PI, reg)
    slot = g4.solid.Box("signal_clamp_slot", 10, 0.901, 0.251, reg)
    cuts = [(hole, [[0, 0, 0], [0.25, 5.05, 0]]), (hole, [[0, 0, 0], [0.25, -5.05, 0]]),
            (slot, [[0, 0, 0], [0, 0, 0]])]
    return common.subtract_all(reg, "signal_clamp_s", solid, cuts)


def hv_clamp_solid(reg):
    block = g4.solid.Box("hv_clamp_block", 13, 13, ref.T_CLAMP, reg)
    hole = g4.solid.Tubs("hv_clamp_hole", 0, 1.5, ref.T_CLAMP + 1, 0, TWO_PI, reg)
    slot = g4.solid.Box("hv_clamp_slot", 13.1, 0.901, 0.251, reg)
    cuts = [(hole, [[0, 0, 0], [-3.45, 4, 0]]), (hole, [[0, 0, 0], [-3.45, -4, 0]]),
            (slot, [[0, 0, 0], [0, 0, 0]])]
    return common.subtract_all(reg, "hv_clamp_s", block, cuts)


def add_front_end(reg, world, mat):
    z = ref.Z_CLAMP
    t, r = ref.T_CABLE, ref.CABLE_BEND_R

    def lv(name, solid, material):
        return g4.LogicalVolume(solid, mat[material], name, reg)

    def place(volume, name, position, rot=(0, 0, 0)):
        g4.PhysicalVolume(list(rot), list(position), volume, name, world, reg)

    # --- clamps, LMFE and springs, all at the height of the clamps
    place(lv("signal_clamp", signal_clamp_solid(reg), "ultem"), "signal_clamp", [0, ref.SIGNAL_R, z], SIGNAL_SIDE)
    place(lv("lmfe", g4.solid.Box("lmfe_s", 16, 8, 0.5, reg), "silica"), "lmfe",
          [0, ref.SIGNAL_R + (7.5 + 16 + 0.1) / 2, z], SIGNAL_SIDE)
    place(lv("hv_clamp", hv_clamp_solid(reg), "ultem"), "hv_clamp", [0, -ref.HV_R, z], HV_SIDE)
    spring = lv("spring", g4.solid.Box("spring_s", 13, 0.9, 0.25, reg), "bronze")
    place(spring, "spring_signal", [0, ref.SIGNAL_R - (13 - 7.5) / 2, z], SIGNAL_SIDE)
    place(spring, "spring_hv", [0, -HV_CABLE_Y0, z], HV_SIDE)

    # --- pins through plate and clamp, with a washer under the clamp
    pin = lv("pin", g4.solid.Tubs("pin_s", 0, 1.3 - 2e-10, ref.PIN_L, 0, TWO_PI, reg), "cu")
    washer = lv("washer", g4.solid.Tubs("washer_s", 1.4, 2.5, ref.T_WASHER, 0, TWO_PI, reg), "bronze")
    pin_below_clamp = ref.PIN_L - ref.T_PEN - ref.T_CLAMP
    for side, holes in (("signal", SIGNAL_PINS), ("hv", HV_PINS)):
        for i, (x, y) in enumerate(holes):
            place(pin, f"pin_{side}_{i}", [x, y, z + ref.T_PEN / 2 - pin_below_clamp / 2])
            place(washer, f"washer_{side}_{i}", [x, y, z - (ref.T_CLAMP + ref.T_WASHER) / 2 - ref.SAFETY])

    # --- cables: flat copper strips, 2 mm wide. A bend is a quarter of a tube.
    def bend(name):
        return lv(name, g4.solid.Tubs(f"{name}_s", r, r + t, ref.CABLE_W, -math.pi / 2, math.pi / 2, reg), "cu")

    def upward(name, bottom):
        length = ref.CABLE_TOP_Z - bottom
        box = g4.solid.Box(f"{name}_s", ref.CABLE_W, t, length, reg)
        return lv(name, box, "cu"), bottom + length / 2

    bend_z = z + r + t / 2                # height of the bend axis; the bend ends there, pointing up

    # signal: from the outer end of the LMFE straight outward, then up
    start, bend_y = SIGNAL_CABLE_Y0 + 16, SIGNAL_CABLE_Y0 + ref.SIGNAL_BEND_X
    flat = g4.solid.Box("signal_cable_flat_s", bend_y - GAP - start, ref.CABLE_W, t, reg)
    place(lv("signal_cable_flat", flat, "cu"), "signal_cable_flat", [0, (start + bend_y - GAP) / 2, z], SIGNAL_SIDE)
    place(bend("signal_cable_bend"), "signal_cable_bend", [0, bend_y, bend_z], SIGNAL_BEND)
    up, up_z = upward("signal_cable_up", bend_z + GAP)
    place(up, "signal_cable_up", [0, bend_y + r + t / 2, up_z])

    # HV: the bend starts at the outer edge of the HV clamp, then up
    bend_y = -(HV_CABLE_Y0 + ref.HV_BEND_X)
    place(bend("hv_cable_bend"), "hv_cable_bend", [0, bend_y, bend_z], HV_BEND)
    up, up_z = upward("hv_cable_up", bend_z + GAP)
    place(up, "hv_cable_up", [0, bend_y - r - t / 2, up_z])
