"""Smoke test 1: build a small detector with pyg4ometry, write GDML, render a cross-section.

An aluminium endcap holds a vacuum, and a germanium crystal sits 5 mm below
the top of the vacuum. All parts are coaxial along z.

    python smoke/01_geometry.py        writes smoke/out/crystal.gdml and crystal.png
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
import pyg4ometry.gdml as gdml
import pyg4ometry.geant4 as g4

OUT = Path(__file__).parent / "out"

# Full lengths and radii in mm.
ENDCAP_R, ENDCAP_L = 51.0, 150.0
VACUUM_R, VACUUM_L = 50.0, 148.0
CRYSTAL_R, CRYSTAL_L = 37.0, 32.0
GAP = 5.0                      # crystal top to vacuum top
CRYSTAL_Z = VACUUM_L / 2 - GAP - CRYSTAL_L / 2   # crystal centre in the vacuum frame

COLOURS = {"G4_AIR": "white", "G4_Al": "silver", "G4_Galactic": "lightblue", "G4_Ge": "seagreen"}


def build():
    reg = g4.Registry()

    def material(name):
        return g4.MaterialPredefined(name, reg)

    def tube(name, radius, length):
        return g4.solid.Tubs(name, 0, radius, length, 0, 2 * math.pi, reg, "mm", "rad")

    world = g4.LogicalVolume(g4.solid.Box("world_s", 400, 400, 400, reg, "mm"),
                             material("G4_AIR"), "world", reg)
    endcap = g4.LogicalVolume(tube("endcap_s", ENDCAP_R, ENDCAP_L), material("G4_Al"), "endcap", reg)
    vacuum = g4.LogicalVolume(tube("vacuum_s", VACUUM_R, VACUUM_L), material("G4_Galactic"), "vacuum", reg)
    crystal = g4.LogicalVolume(tube("crystal_s", CRYSTAL_R, CRYSTAL_L), material("G4_Ge"), "crystal", reg)

    g4.PhysicalVolume([0, 0, 0], [0, 0, 0], endcap, "endcap", world, reg)
    g4.PhysicalVolume([0, 0, 0], [0, 0, 0], vacuum, "vacuum", endcap, reg)
    g4.PhysicalVolume([0, 0, 0], [0, 0, CRYSTAL_Z], crystal, "crystal", vacuum, reg)
    reg.setWorld(world)
    return reg


def write_gdml(reg, path):
    writer = gdml.Writer()
    writer.addDetector(reg)
    writer.write(str(path))


def to_polydata(solid, offset):
    vertices, polygons, _ = solid.mesh().toVerticesAndPolygons()
    faces = np.concatenate([[len(p), *p] for p in polygons])
    return pv.PolyData(np.array(vertices) + offset, faces)


def outlines(mesh):
    """Closed outlines of a mesh in the y = 0 plane, as arrays of (x, z) points."""
    lines = mesh.slice(normal="y", origin=(0, 0, 0)).strip(join=True)
    loops, cells, i = [], lines.lines, 0
    while i < len(cells):
        n = cells[i]
        loops.append(lines.points[cells[i + 1:i + 1 + n]][:, [0, 2]])
        i += n + 1
    return loops


def render(reg, path):
    """Cross-section at y = 0: each part filled in the colour of its material."""
    fig, ax = plt.subplots(figsize=(8, 9))
    labels = []

    def add(lv, offset, depth):
        for daughter in lv.daughterVolumes:
            position = offset + np.array(daughter.position.eval())
            child = daughter.logicalVolume
            mesh = to_polydata(child.solid, position)
            for loop in outlines(mesh):
                ax.fill(loop[:, 0], loop[:, 1], facecolor=COLOURS[child.material.name],
                        edgecolor="black", linewidth=0.8, zorder=depth)
            labels.append((f"{daughter.name} ({child.material.name})", mesh, child))
            add(child, position, depth + 1)

    add(reg.getWorldVolume(), np.zeros(3), 1)

    # Daughters are drawn on top of their mother, so aim each label at the
    # part of the mother that stays visible above its highest daughter.
    tops = {name: mesh.bounds[5] for name, mesh, _ in labels}
    x_text = max(mesh.bounds[1] for _, mesh, _ in labels) * 1.25
    for i, (name, mesh, lv) in enumerate(labels):
        top = mesh.bounds[5]
        inner = [tops[f"{d.name} ({d.logicalVolume.material.name})"] for d in lv.daughterVolumes]
        z = (top + max(inner)) / 2 if inner else (top + mesh.bounds[4]) / 2
        ax.annotate(name, xy=(0.5 * mesh.bounds[1], z), xytext=(x_text, top - 12 * i),
                    fontsize=12, va="center", zorder=100,
                    arrowprops={"arrowstyle": "-", "color": "black", "linewidth": 0.8})

    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    ax.set_title("Cross-section at y = 0")
    ax.margins(0.1)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    reg = build()
    write_gdml(reg, OUT / "crystal.gdml")
    render(reg, OUT / "crystal.png")
    assert (OUT / "crystal.gdml").stat().st_size > 0
    assert (OUT / "crystal.png").stat().st_size > 5000
    print("PASS  wrote", OUT / "crystal.gdml", "and", OUT / "crystal.png")
