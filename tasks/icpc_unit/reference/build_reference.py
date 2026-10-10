"""Reference geometry for task icpc_unit. Hidden from the agent.

One LEGEND-200 detector unit: the inverted-coaxial crystal P43511A with its
PEN baseplate, the three copper rods with brackets and Ultem insulators, the
signal clamp with LMFE, the HV clamp, pins, washers, springs and both cables.

The holder follows the public LEGEND-200 geometry, legend-pygeom-l200
(src/pygeoml200/hpge_strings.py, GPL-3.0): same parts, dimensions and
positions, for a single unit. The baseplate is that package's mesh
models/BasePlate_large.stl. Only the crystal comes from our own source file.

Frame: z = 0 is the bottom face of the crystal, the crystal axis is the z
axis. The signal side is +y, the HV side is -y. Rods are at 0, 120 and 240
degrees, measured from +x towards +y.

    python tasks/icpc_unit/reference/build_reference.py     writes reference.gdml
"""

import math
import sys
from pathlib import Path

import numpy as np
import pyg4ometry
import pyg4ometry.geant4 as g4
from pyg4ometry.transformation import matrix2tbxyz

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
import common  # noqa: E402
from common import TWO_PI  # noqa: E402
from icpc_p43511a.reference import build_reference as icpc  # noqa: E402

# All lengths in mm. Values are those of legend-pygeom-l200 unless marked "chosen".
ROD_POS_R = 46.5            # chosen: rod distance from the axis, as for strings with large plates
ROD_LENGTH_UNIT = 120.0     # chosen: height of one unit along the string
ROD_R = 1.40
ROD_ANGLES = (0, 120, 240)
T_PEN, T_CABLE, T_CLAMP, T_WELD, T_INS, T_WASHER, PIN_L = 1.5, 0.076, 3.7, 1.5, 2.4, 0.3, 7.8
SAFETY = 0.001              # gap between stacked parts
SIGNAL_R, HV_R = 14.25, 37.5          # clamp centres: distance from the axis (large plate)
CABLE_BEND_R = 3.08
HV_BEND_X = 9.5                       # bend start, measured from the HV cable origin
SIGNAL_BEND_X = 16 + 23.25 / 3        # bend start, measured from the signal cable origin
CABLE_W = 2.0
WORLD = 400.0

# Heights of part centres. The crystal rests on the insulators, which lie on the plate.
Z_INS = -T_INS / 2 - SAFETY
Z_PEN = -T_INS - T_PEN / 2 - 2 * SAFETY
Z_WELD = -T_INS - T_PEN - T_WELD / 2 - 3 * SAFETY
Z_CLAMP = -T_INS - T_PEN - T_CLAMP / 2 - 4 * SAFETY
Z_UNIT_BOTTOM = -(3.7 + 1.3 + T_PEN + T_INS)          # -8.9
ROD_Z = (Z_UNIT_BOTTOM - 3.5, Z_UNIT_BOTTOM + ROD_LENGTH_UNIT + 12)
CABLE_TOP_Z = Z_CLAMP + CABLE_BEND_R + ROD_LENGTH_UNIT - 1

ULTEM_DENSITY, PEN_DENSITY, SILICA_DENSITY, PHBR_DENSITY = 1.27, 1.35, 2.20, 8.8   # g/cm3

COLOURS = {"EnrichedGermanium": "#9aa0a6", "G4_Cu": "#c8763a", "PEN": "#d8e6f2",
           "Ultem": "#d9a441", "FusedSilica": "#f4f4f4", "PhosphorBronze": "#a8742a"}


def turn(angle):
    """Placement rotation that turns a part's local x axis to `angle` (degrees) in the x-y plane."""
    return [0, 0, -math.radians(angle)]


def rotation(local_x, local_y):
    """Placement rotation for a part whose local x and y axes should point along the given world axes."""
    x, y = np.array(local_x, float), np.array(local_y, float)
    world_from_local = np.column_stack([x, y, np.cross(x, y)])
    return list(matrix2tbxyz(world_from_local.T))     # pyg4ometry placements take the inverse


def polar(radius, angle, z):
    return [radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)), z]


def materials(reg):
    el = {s: g4.ElementSimple(n, s, z, a, reg) for n, s, z, a in [
        ("Carbon", "C", 6, 12.011), ("Hydrogen", "H", 1, 1.008), ("Oxygen", "O", 8, 15.999),
        ("Nitrogen", "N", 7, 14.007), ("Silicon", "Si", 14, 28.085),
        ("Copper", "Cu", 29, 63.546), ("Tin", "Sn", 50, 118.71)]}

    def compound(name, density, atoms):
        material = g4.MaterialCompound(name, density, len(atoms), reg)
        for symbol, n in atoms.items():
            material.add_element_natoms(el[symbol], n)
        return material

    bronze = g4.MaterialCompound("PhosphorBronze", PHBR_DENSITY, 2, reg)
    bronze.add_element_massfraction(el["Cu"], 0.94)
    bronze.add_element_massfraction(el["Sn"], 0.06)
    return {
        "ge": common.enriched_germanium(reg),
        "cu": g4.MaterialPredefined("G4_Cu", reg),
        "lar": g4.MaterialPredefined("G4_lAr", reg),
        "pen": compound("PEN", PEN_DENSITY, {"C": 14, "H": 10, "O": 4}),
        "ultem": compound("Ultem", ULTEM_DENSITY, {"C": 37, "H": 24, "O": 6, "N": 2}),
        "silica": compound("FusedSilica", SILICA_DENSITY, {"Si": 1, "O": 2}),
        "bronze": bronze,
    }


def bracket_solid(reg):
    """Copper bracket (weldment) under a plate corner: a flap with a block that grips the rod."""
    flap = g4.solid.Box("bracket_flap", 19, 5, T_WELD, reg)
    block = g4.solid.Box("bracket_block", 6.7, 5, 1.5, reg)
    both = g4.solid.Union("bracket_both", flap, block,
                          [[0, 0, 0], [19 / 2 - 6.7 / 2, 0, -1.5 / 2 - T_WELD / 2]], reg)
    hole = g4.solid.Tubs("bracket_hole", 0, 1.6, 2 * (T_WELD + 2.2), 0, TWO_PI, reg)
    return g4.solid.Subtraction("bracket_s", both, hole, [[0, 0, 0], [7, 0, 0]], reg)


def insulator_solid(reg, top_length):
    """Ultem insulator: a flap under the crystal edge with a block that stands beside the crystal."""
    flap = g4.solid.Box("insulator_flap", 16.5, 7, T_INS, reg)
    block = g4.solid.Box("insulator_block", top_length, 7, 5.5 - T_INS, reg)
    both = g4.solid.Union("insulator_both", flap, block,
                          [[0, 0, 0], [16.5 / 2 - top_length / 2, 0, 5.5 / 2]], reg)
    hole = g4.solid.Tubs("insulator_hole", 0, 1.6, 3 * 5.5, 0, TWO_PI, reg)
    return g4.solid.Subtraction("insulator_s", both, hole, [[0, 0, 0], [16.5 / 2 - 1.5, 0, 0]], reg)


def build(parts="all"):
    reg = g4.Registry()
    mat = materials(reg)
    world = g4.LogicalVolume(g4.solid.Box("world_s", WORLD, WORLD, WORLD, reg), mat["lar"], "world", reg)

    def lv(name, solid, material):
        return g4.LogicalVolume(solid, mat[material], name, reg)

    def place(volume, name, position, rot=(0, 0, 0)):
        g4.PhysicalVolume(list(rot), list(position), volume, name, world, reg)

    place(lv("crystal", icpc.crystal_solid(reg), "ge"), "crystal", [0, 0, icpc.HEIGHT / 2])

    plate = pyg4ometry.stl.Reader(str(HERE / "models" / "BasePlate_large.stl"), solidname="pen_plate_s",
                                  centre=False, registry=reg).getSolid()
    place(lv("pen_plate", plate, "pen"), "pen_plate", [0, 0, Z_PEN])

    rod = lv("rod", g4.solid.Tubs("rod_s", 0, ROD_R, ROD_Z[1] - ROD_Z[0], 0, TWO_PI, reg), "cu")
    bracket = lv("bracket", bracket_solid(reg), "cu")
    # the block of the insulator ends 0.25 mm from the crystal side
    insulator = lv("insulator", insulator_solid(reg, ROD_POS_R - icpc.RADIUS + 1.5 - 0.25), "ultem")
    for i, angle in enumerate(ROD_ANGLES):
        place(rod, f"rod_{i}", polar(ROD_POS_R, angle, sum(ROD_Z) / 2))
        place(bracket, f"bracket_{i}", polar(ROD_POS_R - 7, angle, Z_WELD), turn(angle))
        place(insulator, f"insulator_{i}", polar(ROD_POS_R - (16.5 / 2 - 1.5), angle, Z_INS), turn(angle))

    if parts == "all":
        from front_end import add_front_end   # clamps, LMFE, pins, washers, springs, cables
        add_front_end(reg, world, mat)

    reg.setWorld(world)
    return reg


if __name__ == "__main__":
    common.write(build(), HERE / "reference.gdml")
    print("wrote", HERE / "reference.gdml")
