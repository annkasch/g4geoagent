"""3D pictures of the icpc_unit reference, for people. Not used by any check.

    python tasks/icpc_unit/reference/render_3d.py     writes reference_3d_*.png
"""

import os
from pathlib import Path

os.environ.pop("DISPLAY", None)   # a forwarded X display can crash off-screen rendering

import numpy as np
import pyg4ometry.config as config
import pyvista as pv

# finer meshes than the default, so round parts look round
for solid in (config.SolidDefaults.Tubs, config.SolidDefaults.Polycone, config.SolidDefaults.Orb,
              config.SolidDefaults.Torus):
    solid.nslice = 96
    if hasattr(solid, "nstack"):
        solid.nstack = 48

import build_reference as ref  # noqa: E402

HERE = Path(__file__).parent
LOOK = {   # material: (colour, opacity)
    "EnrichedGermanium": ("#9aa0a6", 1.0),
    "G4_Cu": ("#c8763a", 1.0),
    "PEN": ("#d8e6f2", 0.55),
    "FusedSilica": ("#f2f2f2", 1.0),
    "Ultem": ("#e0a030", 0.6),
    "CoaxCable": ("#b05a20", 1.0),
    "G4_KAPTON": ("#e8b400", 1.0),
}
VIEWS = {   # name: camera position, looking at the middle of the unit
    "below": (150, -190, -150),
    "above": (150, -190, 230),
    "hv_side": (-110, 230, -110),
}


def meshes(lv, offset=np.zeros(3)):
    """Material and mesh of every placed volume below lv, in world coordinates."""
    for placed in lv.daughterVolumes:
        child = placed.logicalVolume
        vertices, polygons, _ = child.solid.mesh().toVerticesAndPolygons()
        faces = np.concatenate([[len(p), *p] for p in polygons])
        mesh = pv.PolyData(np.array(vertices), faces).triangulate().clean()
        # only rotations about x occur in this geometry (cylinders laid along y)
        mesh = mesh.rotate_x(np.degrees(placed.rotation.eval()[0]))
        position = offset + np.array(placed.position.eval())
        yield child.material.name, mesh.translate(position)
        yield from meshes(child, position)


if __name__ == "__main__":
    parts = list(meshes(ref.build().getWorldVolume()))
    for name, camera in VIEWS.items():
        plotter = pv.Plotter(off_screen=True, window_size=(1000, 1200))
        plotter.set_background("white")
        for material, mesh in parts:
            colour, opacity = LOOK[material]
            plotter.add_mesh(mesh, color=colour, opacity=opacity, smooth_shading=True,
                             split_sharp_edges=True, specular=0.3)
        plotter.camera_position = [camera, (0, 0, 50), (0, 0, 1)]
        plotter.screenshot(str(HERE / f"reference_3d_{name}.png"))
        plotter.close()
        print("wrote", HERE / f"reference_3d_{name}.png")
