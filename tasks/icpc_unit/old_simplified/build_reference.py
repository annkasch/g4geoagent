"""Reference geometry for task icpc_unit. Hidden from the agent.

A simplified LEGEND-200 detector unit: the inverted-coaxial crystal P43511A
resting on three supports on a triangular PEN baseplate, three copper rods, the
front-end substrate (LMFE) in its frame under the plate, four signal cables
and a high-voltage cable.

Only the crystal has real dimensions. The plate thickness and the LMFE size
are published values; everything else is estimated from pictures and
simplified (see meta.yaml).

Frame: as in task icpc_p43511a. z = 0 is the bottom face of the crystal, the
crystal axis is the world z axis. Angles are measured from +x towards +y.

    python tasks/icpc_unit/reference/build_reference.py     writes reference.gdml
"""

import math
import sys
from pathlib import Path

import pyg4ometry.geant4 as g4

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
import common  # noqa: E402
from common import OVER, TWO_PI  # noqa: E402
from icpc_p43511a.reference import build_reference as icpc  # noqa: E402

# All lengths in mm, angles in degrees.
GAP = 2.0                                   # crystal bottom face to plate top face
PLATE_R, PLATE_T, PLATE_HOLE_R = 46.0, 1.5, 8.0
PLATE_SIDE_DIST, PLATE_SIDE_ANGLES = 30.0, (60, 180, 300)   # straight edges: distance from the axis, direction they face
SUPPORT_R, SUPPORT_POS_R, SUPPORT_ANGLES = 3.0, 25.0, (60, 180, 300)   # height = GAP
ROD_R, ROD_L, ROD_POS_R, ROD_ANGLES = 1.5, 130.0, 41.0, (0, 120, 240)
ROD_BOTTOM_Z = -12.0
ROD_HOLE_R = 1.6                            # holes in the plate for the rods
LMFE_X, LMFE_Y, LMFE_T = 8.0, 16.0, 0.5       # fused-silica substrate, enclosed in the frame
FRAME_X, FRAME_Y, FRAME_T = 11.0, 20.0, 1.5  # Ultem frame, flat against the plate underside
LMFE_CENTRE_Y = -18.0                       # frame and substrate are centred on x = 0
# Signal cables: four coaxial cables, each modelled as two straight pieces. One
# runs outwards from the end of the frame, the other up past the crystal.
CABLE_R, CABLE_XS = 0.2, (-0.9, -0.3, 0.3, 0.9)
CABLE_UP_Y = -38.0                          # y of the vertical pieces
# High-voltage cable: a flat Kapton strip, modelled as two straight pieces. One
# lies against the plate underside, the other runs up past the crystal.
HV_W, HV_T = 3.0, 0.125                     # width (along x) and thickness of the strip
HV_UP_Y = 37.5                              # y of the centre of the upward piece
HV_OUT_START_Y = 20.0                       # inner end of the piece under the plate
WORLD = 300.0

PLATE_TOP_Z = -GAP
PLATE_BOTTOM_Z = PLATE_TOP_Z - PLATE_T
FRAME_CENTRE_Z = PLATE_BOTTOM_Z - FRAME_T / 2           # -4.25, also the height of the outward cable pieces
ROD_TOP_Z = ROD_BOTTOM_Z + ROD_L                        # 118, rods and cables end here
CABLE_OUT_Y = (LMFE_CENTRE_Y - FRAME_Y / 2, CABLE_UP_Y + CABLE_R)   # from the frame end to the vertical piece
CABLE_OUT_L = CABLE_OUT_Y[0] - CABLE_OUT_Y[1]           # 9.8
CABLE_UP_BOTTOM_Z = FRAME_CENTRE_Z - CABLE_R            # -4.45
CABLE_UP_L = ROD_TOP_Z - CABLE_UP_BOTTOM_Z              # 122.45
HV_OUT_L = HV_UP_Y - HV_T / 2 - HV_OUT_START_Y          # 17.4375, ends at the upward piece
HV_UP_BOTTOM_Z = PLATE_BOTTOM_Z - HV_T                  # -3.625
HV_UP_L = ROD_TOP_Z - HV_UP_BOTTOM_Z                    # 121.625

PEN_DENSITY, SILICA_DENSITY, CU_DENSITY = 1.35, 2.20, 8.96    # g/cm3
ULTEM_DENSITY, CABLE_DENSITY, KAPTON_DENSITY = 1.27, 3.0, 1.42


def xy(radius, angle):
    return [radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle))]


def masses_g():
    """Mass of every part in g, from the dimensions above."""
    # each straight edge cuts a circular segment off the disc
    segment = (PLATE_R**2 * math.acos(PLATE_SIDE_DIST / PLATE_R)
               - PLATE_SIDE_DIST * math.sqrt(PLATE_R**2 - PLATE_SIDE_DIST**2))
    plate = (math.pi * (PLATE_R**2 - PLATE_HOLE_R**2) - 3 * segment
             - 3 * math.pi * ROD_HOLE_R**2) * PLATE_T
    support = math.pi * SUPPORT_R**2 * GAP
    rod = math.pi * ROD_R**2 * ROD_L
    lmfe = LMFE_X * LMFE_Y * LMFE_T
    masses = {
        "crystal": icpc.analytic_volume() * common.GE_DENSITY,
        "pen_plate": plate * PEN_DENSITY,
        "lmfe": lmfe * SILICA_DENSITY,
        "lmfe_frame": (FRAME_X * FRAME_Y * FRAME_T - lmfe) * ULTEM_DENSITY,
        "hv_out": HV_W * HV_T * HV_OUT_L * KAPTON_DENSITY,
        "hv_up": HV_W * HV_T * HV_UP_L * KAPTON_DENSITY,
    }
    for i in range(len(CABLE_XS)):
        masses[f"signal_out_{i}"] = math.pi * CABLE_R**2 * CABLE_OUT_L * CABLE_DENSITY
        masses[f"signal_up_{i}"] = math.pi * CABLE_R**2 * CABLE_UP_L * CABLE_DENSITY
    for i in range(3):
        masses[f"support_{i}"] = support * PEN_DENSITY
        masses[f"rod_{i}"] = rod * CU_DENSITY
    return {name: mass / 1000 for name, mass in masses.items()}


def materials(reg):
    carbon = g4.ElementSimple("Carbon", "C", 6, 12.011, reg)
    hydrogen = g4.ElementSimple("Hydrogen", "H", 1, 1.008, reg)
    oxygen = g4.ElementSimple("Oxygen", "O", 8, 15.999, reg)
    silicon = g4.ElementSimple("Silicon", "Si", 14, 28.085, reg)
    pen = g4.MaterialCompound("PEN", PEN_DENSITY, 3, reg)          # C14 H10 O4
    pen.add_element_natoms(carbon, 14)
    pen.add_element_natoms(hydrogen, 10)
    pen.add_element_natoms(oxygen, 4)
    silica = g4.MaterialCompound("FusedSilica", SILICA_DENSITY, 2, reg)   # Si O2
    silica.add_element_natoms(silicon, 1)
    silica.add_element_natoms(oxygen, 2)
    nitrogen = g4.ElementSimple("Nitrogen", "N", 7, 14.007, reg)
    fluorine = g4.ElementSimple("Fluorine", "F", 9, 18.998, reg)
    cu = g4.ElementSimple("Copper", "Cu", 29, 63.546, reg)
    ultem = g4.MaterialCompound("Ultem", ULTEM_DENSITY, 4, reg)     # polyetherimide, C37 H24 O6 N2
    ultem.add_element_natoms(carbon, 37)
    ultem.add_element_natoms(hydrogen, 24)
    ultem.add_element_natoms(oxygen, 6)
    ultem.add_element_natoms(nitrogen, 2)
    # coaxial cable smeared into one material: half copper, half FEP (C F2) by mass
    cable = g4.MaterialCompound("CoaxCable", CABLE_DENSITY, 3, reg)
    fep_c = 12.011 / (12.011 + 2 * 18.998)
    cable.add_element_massfraction(cu, 0.5)
    cable.add_element_massfraction(carbon, 0.5 * fep_c)
    cable.add_element_massfraction(fluorine, 0.5 * (1 - fep_c))
    return {"pen": pen, "silica": silica, "copper": g4.MaterialPredefined("G4_Cu", reg),
            "ultem": ultem, "cable": cable, "kapton": g4.MaterialPredefined("G4_KAPTON", reg)}


def build():
    reg = g4.Registry()
    mat = materials(reg)
    pen, silica, copper = mat["pen"], mat["silica"], mat["copper"]
    world = g4.LogicalVolume(g4.solid.Box("world_s", WORLD, WORLD, WORLD, reg),
                             g4.MaterialPredefined("G4_lAr", reg), "world", reg)

    def place(lv, name, x, y, z):
        g4.PhysicalVolume([0, 0, 0], [x, y, z], lv, name, world, reg)

    crystal = g4.LogicalVolume(icpc.crystal_solid(reg), common.enriched_germanium(reg), "crystal", reg)
    place(crystal, "crystal", 0, 0, icpc.HEIGHT / 2)

    # Baseplate: a disc cut off along three straight edges, which leaves a
    # triangle with rounded corners, with a central hole and one hole per rod.
    disc = g4.solid.Tubs("plate_disc", PLATE_HOLE_R, PLATE_R, PLATE_T, 0, TWO_PI, reg)
    depth = PLATE_R                      # radial size of the block that cuts one edge
    block = g4.solid.Box("plate_side", depth, 3 * PLATE_R, PLATE_T + 2 * OVER, reg)
    sides = [(block, [[0, 0, math.radians(a)], [*xy(PLATE_SIDE_DIST + depth / 2, a), 0]])
             for a in PLATE_SIDE_ANGLES]
    hole = g4.solid.Tubs("rod_hole", 0, ROD_HOLE_R, PLATE_T + 2 * OVER, 0, TWO_PI, reg)
    holes = [(hole, [[0, 0, 0], [*xy(ROD_POS_R, a), 0]]) for a in ROD_ANGLES]
    plate = g4.LogicalVolume(common.subtract_all(reg, "plate_s", disc, sides + holes),
                             pen, "pen_plate", reg)
    place(plate, "pen_plate", 0, 0, PLATE_TOP_Z - PLATE_T / 2)

    support = g4.LogicalVolume(g4.solid.Tubs("support_s", 0, SUPPORT_R, GAP, 0, TWO_PI, reg),
                               pen, "support", reg)
    for i, angle in enumerate(SUPPORT_ANGLES):
        place(support, f"support_{i}", *xy(SUPPORT_POS_R, angle), -GAP / 2)

    rod = g4.LogicalVolume(g4.solid.Tubs("rod_s", 0, ROD_R, ROD_L, 0, TWO_PI, reg), copper, "rod", reg)
    for i, angle in enumerate(ROD_ANGLES):
        place(rod, f"rod_{i}", *xy(ROD_POS_R, angle), ROD_BOTTOM_Z + ROD_L / 2)

    # LMFE: the substrate sits in the middle of its frame, as a daughter volume.
    frame = g4.LogicalVolume(g4.solid.Box("frame_s", FRAME_X, FRAME_Y, FRAME_T, reg),
                             mat["ultem"], "lmfe_frame", reg)
    lmfe = g4.LogicalVolume(g4.solid.Box("lmfe_s", LMFE_X, LMFE_Y, LMFE_T, reg), silica, "lmfe", reg)
    g4.PhysicalVolume([0, 0, 0], [0, 0, 0], lmfe, "lmfe", frame, reg)
    place(frame, "lmfe_frame", 0, LMFE_CENTRE_Y, FRAME_CENTRE_Z)

    out = g4.LogicalVolume(g4.solid.Tubs("signal_out_s", 0, CABLE_R, CABLE_OUT_L, 0, TWO_PI, reg),
                           mat["cable"], "signal_out", reg)
    up = g4.LogicalVolume(g4.solid.Tubs("signal_up_s", 0, CABLE_R, CABLE_UP_L, 0, TWO_PI, reg),
                          mat["cable"], "signal_up", reg)
    for i, x in enumerate(CABLE_XS):
        # the outward piece lies along y: turn the cylinder axis from z to y
        g4.PhysicalVolume([math.pi / 2, 0, 0], [x, sum(CABLE_OUT_Y) / 2, FRAME_CENTRE_Z],
                          out, f"signal_out_{i}", world, reg)
        place(up, f"signal_up_{i}", x, CABLE_UP_Y, CABLE_UP_BOTTOM_Z + CABLE_UP_L / 2)

    hv_out = g4.LogicalVolume(g4.solid.Box("hv_out_s", HV_W, HV_OUT_L, HV_T, reg),
                              mat["kapton"], "hv_out", reg)
    place(hv_out, "hv_out", 0, HV_OUT_START_Y + HV_OUT_L / 2, PLATE_BOTTOM_Z - HV_T / 2)
    hv_up = g4.LogicalVolume(g4.solid.Box("hv_up_s", HV_W, HV_T, HV_UP_L, reg),
                             mat["kapton"], "hv_up", reg)
    place(hv_up, "hv_up", 0, HV_UP_Y, HV_UP_BOTTOM_Z + HV_UP_L / 2)

    reg.setWorld(world)
    return reg


if __name__ == "__main__":
    common.write(build(), HERE / "reference.gdml")
    print("wrote", HERE / "reference.gdml")
    for name, mass in masses_g().items():
        print(f"  {name:10s} {mass:9.3f} g")
