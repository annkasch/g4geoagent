"""3D pictures of a GDML file, for people to judge a geometry by eye.

    python -m g4geoagent.inspector.render3d <file.gdml> <output folder> [title]

Writes a series of pictures that zoom in step by step. Each step comes twice:
"cut" has the front half removed, so that one sees inside; "contents" hides the
volumes that enclose the view and shows what is in them, uncut.
"""

import os
import sys
from pathlib import Path

os.environ.pop("DISPLAY", None)   # a forwarded X display can crash off-screen rendering

import numpy as np
import pyg4ometry.config as config
import pyg4ometry.gdml as gdml
import pyvista as pv
from pyg4ometry.transformation import tbxyz2matrix

for _solid in (config.SolidDefaults.Tubs, config.SolidDefaults.Cons, config.SolidDefaults.Polycone,
               config.SolidDefaults.Orb, config.SolidDefaults.Sphere, config.SolidDefaults.Torus):
    _solid.nslice = 64            # so that round parts look round
    if hasattr(_solid, "nstack"):
        _solid.nstack = 32

# (words in the material name, colour, opacity). The first line that fits is used.
LOOKS = [
    (("galactic", "vacuum"), "#ffffff", 0.0), (("air",), "#ffffff", 0.0),
    (("water", "ice"), "#4a90d9", 0.13), (("lar", "argon"), "#7fd6c2", 0.16), (("xe", "xenon"), "#b48ead", 0.16),
    (("lN2", "nitrogen"), "#cfe8f3", 0.16), (("gas",), "#e8e2c0", 0.15),
    (("stainless", "steel", "iron", "g4_fe"), "#8d99a6", 1.0), (("cu", "copper"), "#c8752d", 1.0),
    (("pb", "lead"), "#4f5560", 1.0), (("al", "alumin"), "#c9ced6", 1.0),
    (("ge", "germanium", "%"), "#2f3e9e", 1.0), (("si", "silicon"), "#3f8f4f", 1.0),
    (("glass", "pyrex", "boro"), "#f2c14e", 0.9), (("scint", "polystyrene", "vinyltoluene"), "#e8559a", 0.9),
    (("nylon", "pen", "poly", "plastic", "teflon", "ptfe", "kapton", "mylar", "acryl", "plexi"), "#d9a05b", 0.55),
]
OTHERS = ["#9467bd", "#17becf", "#bcbd22", "#e377c2", "#8c564b", "#ff7f0e", "#1f77b4", "#d62728"]


def look(material, others):
    name = material.lower().replace("g4_", "")
    for words, colour, opacity in LOOKS:
        if any(name == w.lower() or (len(w) > 2 and w.lower() in name) for w in words):
            return colour, opacity
    if material not in others:
        others[material] = OTHERS[len(others) % len(OTHERS)]
    return others[material], 1.0


def placed_meshes(gdml_path):
    """Every placed volume of the file: [{name, material, depth, mesh in world coordinates}]."""
    world = gdml.Reader(str(gdml_path)).getRegistry().getWorldVolume()
    cache, parts = {}, []

    def walk(lv, rotation, shift, depth):
        for placed in lv.daughterVolumes:
            child = placed.logicalVolume
            if child.name not in cache:
                vertices, polygons, _ = child.solid.mesh().toVerticesAndPolygons()
                faces = np.concatenate([[len(p), *p] for p in polygons])
                cache[child.name] = pv.PolyData(np.array(vertices, float), faces).triangulate().clean()
            local = tbxyz2matrix(placed.rotation.eval()).T
            here_rotation = rotation @ local
            here_shift = rotation @ np.array(placed.position.eval(), float) + shift
            mesh = cache[child.name].copy()
            mesh.points = mesh.points @ here_rotation.T + here_shift
            parts.append({"name": placed.name, "material": child.material.name, "depth": depth, "mesh": mesh,
                          "container": bool(child.daughterVolumes)})
            walk(child, here_rotation, here_shift, depth + 1)

    walk(world, np.eye(3), np.zeros(3), 1)
    return parts


def _bounds(parts):
    b = np.array([p["mesh"].bounds for p in parts])
    return np.array([b[:, 0].min(), b[:, 1].max(), b[:, 2].min(), b[:, 3].max(), b[:, 4].min(), b[:, 5].max()])


def _size(bounds):
    return float(np.linalg.norm(bounds[1::2] - bounds[0::2]))


def zoom_steps(parts, factor=1.8, most=4):
    """Depths at which the picture gets clearly smaller: [(depth, bounds of everything at least that deep)]."""
    steps, last = [], None
    for depth in sorted({p["depth"] for p in parts}):
        bounds = _bounds([p for p in parts if p["depth"] >= depth])
        if last is None or _size(bounds) * factor < last:
            steps.append((depth, bounds))
            last = _size(bounds)
    return steps[:most]


def _picture(parts, bounds, path, title, cut, others):
    """One picture of the parts inside `bounds`.

    cut      the half towards the camera is removed. Volumes that hold other volumes are drawn as
             open shells, so that one looks into them; the others are closed off at the cut.
    not cut  volumes that enclose the whole view are left out, volumes that hold others are see-through.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    plotter = pv.Plotter(off_screen=True, window_size=(1500, 1500))
    plotter.set_background("white")
    centre, half = (bounds[0::2] + bounds[1::2]) / 2, (bounds[1::2] - bounds[0::2]) / 2
    legend = {}
    for part in parts:
        colour, opacity = look(part["material"], others)
        mesh, b = part["mesh"], np.array(part["mesh"].bounds)
        if b[1] < bounds[0] or b[0] > bounds[1] or b[3] < bounds[2] or b[2] > bounds[3] or b[5] < bounds[4] or b[4] > bounds[5]:
            continue                                   # outside the view
        if opacity == 0.0:
            continue
        encloses = bool(np.all(b[0::2] <= bounds[0::2] + 1e-6) and np.all(b[1::2] >= bounds[1::2] - 1e-6))
        fluid = opacity < 0.5
        if cut:
            closed = None
            if not part["container"]:
                try:
                    closed = mesh.clip_closed_surface(normal=(0, 1, 0), origin=centre)
                except Exception:
                    closed = None
            mesh = closed if closed is not None and closed.n_points else mesh.clip(normal=(0, -1, 0), origin=centre)
            if mesh.n_points == 0:
                continue
            opacity = 0.10 if fluid else 1.0
        else:
            if encloses and (part["container"] or fluid):
                continue
            # a part that spans most of the view in two directions wraps what one wants to see
            wraps = sum((b[1::2] - b[0::2]) > 0.6 * 2 * half) >= 2
            opacity = 0.10 if fluid else (0.20 if part["container"] or wraps else 1.0)
        solid = opacity == 1.0
        plotter.add_mesh(mesh, color=colour, opacity=opacity, smooth_shading=solid, split_sharp_edges=solid,
                         specular=0.2 if solid else 0.0, show_edges=False)
        edges = mesh.extract_feature_edges(feature_angle=35, boundary_edges=True, manifold_edges=False)
        if edges.n_points:
            plotter.add_mesh(edges, color="#1a1a1a", line_width=1.4 if solid else 0.9, opacity=0.75 if solid else 0.4)
        legend[part["material"]] = colour
    reach = 2.9 * float(np.linalg.norm(half))
    plotter.camera_position = [tuple(centre + reach * np.array([0.42, -0.80, 0.42])), tuple(centre), (0, 0, 1)]
    plotter.camera.view_angle = 30
    image = plotter.screenshot(return_img=True)
    plotter.close()

    big = max(half) > 500
    extent = " x ".join(f"{2 * h / 1000:.2f}" if big else f"{2 * h:.0f}" for h in half)
    figure, axis = plt.subplots(figsize=(13, 10))
    axis.imshow(image)
    axis.axis("off")
    axis.set_title(f"{title}\nregion shown: {extent} {'m' if big else 'mm'} (x, y, z). "
                   + ("Front half removed." if cut else "Enclosing volumes hidden, containers see-through."),
                   fontsize=12, loc="left")
    axis.legend(handles=[Patch(facecolor=colour, edgecolor="#333333", label=name[:48]) for name, colour in legend.items()],
                loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=10, title="Material", frameon=False)
    figure.savefig(path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def render(gdml_path, folder, title=None):
    """Write the pictures of `gdml_path` into `folder`. Returns their paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    parts, others, written = placed_meshes(gdml_path), {}, []
    title = title or Path(gdml_path).name
    for number, (depth, bounds) in enumerate(zoom_steps(parts), 1):
        for kind, cut in (("cut", True), ("contents", False)):
            path = folder / f"view{number}_{kind}.png"
            _picture(parts, bounds, path, f"{title} - step {number}", cut, others)
            written.append(path)
    return written


if __name__ == "__main__":
    for picture in render(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None):
        print("wrote", picture)
