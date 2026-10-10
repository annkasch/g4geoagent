"""Reference geometry for task icpc_p43511a. Hidden from the agent.

Inverted-coaxial HPGe detector P43511A, hand-built from the dimensions in
source/IC_section.json. All curved surfaces are exact Geant4 primitives
(cone, sphere, torus), not polygon approximations.

Frame: z = 0 is the bottom face (point contact and groove), the borehole
opens at the top, z = HEIGHT. The crystal axis is the world z axis.

    python tasks/icpc_p43511a/reference/build_reference.py     writes reference.gdml
"""

import math
import sys
from pathlib import Path

import pyg4ometry.geant4 as g4

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
import common  # noqa: E402
from common import OVER, TWO_PI  # noqa: E402

# All lengths in mm.
RADIUS, HEIGHT = 35.9, 99.3
BORE_R_BOTTOM, BORE_R_TOP = 5.0, 13.8     # borehole radius in the straight part, and at the top face
BORE_CONE_H, BORE_TUBE_H = 50.0, 20.0     # tapered part, straight part; a hemisphere closes it
EDGE_R = 2.0                              # rounding of the outer top and bottom edges
GROOVE_R_IN, GROOVE_R_OUT, GROOVE_DEPTH = 13.0, 16.0, 2.0
DIMPLE_R = 1.0                            # hemispherical dimple of the point contact
WORLD = 300.0                             # liquid argon cube, full edge length

BORE_CONE_Z = HEIGHT - BORE_CONE_H                 # 49.3: taper meets straight part
BORE_TUBE_Z = BORE_CONE_Z - BORE_TUBE_H            # 29.3: straight part meets hemisphere
BORE_SLOPE = (BORE_R_TOP - BORE_R_BOTTOM) / BORE_CONE_H


def analytic_volume():
    """Germanium volume in mm3, from the dimensions above."""
    cylinder = math.pi * RADIUS**2 * HEIGHT
    taper = math.pi * BORE_CONE_H / 3 * (BORE_R_BOTTOM**2 + BORE_R_BOTTOM * BORE_R_TOP + BORE_R_TOP**2)
    straight = math.pi * BORE_R_BOTTOM**2 * BORE_TUBE_H
    bore_end = 2 / 3 * math.pi * BORE_R_BOTTOM**3
    groove = math.pi * (GROOVE_R_OUT**2 - GROOVE_R_IN**2) * GROOVE_DEPTH
    dimple = 2 / 3 * math.pi * DIMPLE_R**3
    return (cylinder - taper - straight - bore_end - groove - dimple
            - 2 * common.edge_volume(RADIUS, EDGE_R))


def crystal_solid(reg):
    """The crystal as a solid centred on its own mid-height."""
    mid = HEIGHT / 2          # solids are centred, so the bottom face is at -mid

    def at(z):
        """Transform that puts a cutter's origin at height z above the bottom face."""
        return [[0, 0, 0], [0, 0, z - mid]]

    body = g4.solid.Tubs("body", 0, RADIUS, HEIGHT, 0, TWO_PI, reg)

    # Borehole: straight part and taper as one solid, continued above the top
    # face along the same slope, plus a sphere for the rounded end.
    bore = g4.solid.Polycone(
        "bore_wall", 0, TWO_PI,
        [BORE_TUBE_Z, BORE_CONE_Z, HEIGHT + OVER], [0, 0, 0],
        [BORE_R_BOTTOM, BORE_R_BOTTOM, BORE_R_TOP + BORE_SLOPE * OVER], reg)
    bore_end = g4.solid.Orb("bore_end", BORE_R_BOTTOM, reg)
    bore = g4.solid.Union("bore", bore, bore_end, [[0, 0, 0], [0, 0, BORE_TUBE_Z]], reg)

    groove = g4.solid.Tubs("groove", GROOVE_R_IN, GROOVE_R_OUT, GROOVE_DEPTH + OVER, 0, TWO_PI, reg)
    dimple = g4.solid.Orb("dimple", DIMPLE_R, reg)

    cuts = [
        (bore, at(0)),                                  # polycone z planes are already absolute
        (groove, at((GROOVE_DEPTH - OVER) / 2)),
        (dimple, at(0)),
        *common.edge_cuts(reg, RADIUS, HEIGHT, EDGE_R),
    ]
    return common.subtract_all(reg, "crystal_s", body, cuts)


def build():
    reg = g4.Registry()
    world = g4.LogicalVolume(g4.solid.Box("world_s", WORLD, WORLD, WORLD, reg),
                             g4.MaterialPredefined("G4_lAr", reg), "world", reg)
    crystal = g4.LogicalVolume(crystal_solid(reg), common.enriched_germanium(reg), "crystal", reg)
    g4.PhysicalVolume([0, 0, 0], [0, 0, HEIGHT / 2], crystal, "crystal", world, reg)
    reg.setWorld(world)
    return reg


if __name__ == "__main__":
    common.write(build(), HERE / "reference.gdml")
    volume = analytic_volume() / 1000
    print(f"wrote {HERE / 'reference.gdml'}: germanium volume {volume:.3f} cm3, "
          f"density {common.GE_DENSITY:.4f} g/cm3, mass {volume * common.GE_DENSITY:.1f} g")
