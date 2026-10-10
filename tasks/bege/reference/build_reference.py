"""Reference geometry for task bege. Hidden from the agent.

Broad-energy germanium (BEGe) detector, hand-built from the dimensions in
source/BeGe.json: a short cylinder with rounded edges and a groove.

Frame: z = 0 is the bottom face (point contact and groove), the top face is
at z = HEIGHT. The crystal axis is the world z axis.

    python tasks/bege/reference/build_reference.py     writes reference.gdml
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
RADIUS, HEIGHT = 35.9, 40.0
EDGE_R = 2.0                              # rounding of the outer top and bottom edges
GROOVE_R_IN, GROOVE_R_OUT, GROOVE_DEPTH = 7.0, 10.0, 2.0
WORLD = 300.0                             # liquid argon cube, full edge length


def analytic_volume():
    """Germanium volume in mm3, from the dimensions above."""
    cylinder = math.pi * RADIUS**2 * HEIGHT
    groove = math.pi * (GROOVE_R_OUT**2 - GROOVE_R_IN**2) * GROOVE_DEPTH
    return cylinder - groove - 2 * common.edge_volume(RADIUS, EDGE_R)


def crystal_solid(reg):
    """The crystal as a solid centred on its own mid-height."""
    body = g4.solid.Tubs("body", 0, RADIUS, HEIGHT, 0, TWO_PI, reg)
    groove = g4.solid.Tubs("groove", GROOVE_R_IN, GROOVE_R_OUT, GROOVE_DEPTH + OVER, 0, TWO_PI, reg)
    cuts = [
        (groove, [[0, 0, 0], [0, 0, (GROOVE_DEPTH - OVER) / 2 - HEIGHT / 2]]),
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
