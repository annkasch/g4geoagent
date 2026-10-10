"""3D pictures of the icpc_unit reference, for people. Not used by any check.

    python tasks/icpc_unit/reference/render_3d.py     writes reference_3d_*.png
"""

import os
from pathlib import Path

os.environ.pop("DISPLAY", None)   # a forwarded X display can crash off-screen rendering

import numpy as np
import pyg4ometry.config as config
import pyvista as pv
from pyg4ometry.transformation import tbxyz2matrix

# finer meshes than the default, so round parts look round
for solid in (config.SolidDefaults.Tubs, config.SolidDefaults.Polycone, config.SolidDefaults.Orb,
              config.SolidDefaults.Torus):
    solid.nslice = 96
    if hasattr(solid, "nstack"):
        solid.nstack = 48

import build_reference as ref  # noqa: E402

HERE = Path(__file__).parent
OPACITY = {"PEN": 0.45}
VIEWS = {   # name: (camera position, point it looks at)
    "below": ((150, -200, -160), (0, 0, 45)),
    "below_close": ((70, -95, -105), (0, 0, -3)),
    "side": ((230, 120, 60), (0, 0, 50)),
}


def meshes(lv):
    """Material and mesh, in world coordinates, of every volume placed in lv."""
    for placed in lv.daughterVolumes:
        child = placed.logicalVolume
        vertices, polygons, _ = child.solid.mesh().toVerticesAndPolygons()
        faces = np.concatenate([[len(p), *p] for p in polygons])
        world_from_local = tbxyz2matrix(placed.rotation.eval()).T
        points = np.array(vertices) @ world_from_local.T + np.array(placed.position.eval())
        yield child.material.name, pv.PolyData(points, faces).triangulate().clean()


if __name__ == "__main__":
    parts = list(meshes(ref.build().getWorldVolume()))
    for name, (camera, focus) in VIEWS.items():
        plotter = pv.Plotter(off_screen=True, window_size=(1100, 1100))
        plotter.set_background("white")
        for material, mesh in parts:
            plotter.add_mesh(mesh, color=ref.COLOURS[material], opacity=OPACITY.get(material, 1.0),
                             smooth_shading=True, split_sharp_edges=True, specular=0.3)
        plotter.camera_position = [camera, focus, (0, 0, 1)]
        plotter.screenshot(str(HERE / f"reference_3d_{name}.png"))
        plotter.close()
        print("wrote", HERE / f"reference_3d_{name}.png")
