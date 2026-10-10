"""Cross-section pictures drawn from Geant4 line scans, coloured by material."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from g4geoagent.inspector.geant4_run import geant4_run


def cross_section(gdml_path, png_path, x_range, z_range, columns=400, title=None, y=0.0,
                  figsize=(8, 9), timeout=600):
    """Draw the x-z plane at height `y` by firing one geantino down each column.

    x_range, z_range: (min, max) in mm, inside the world volume. Boundaries
    along z are exact; the resolution along x is the column width.
    Returns the Geant4 report.
    """
    width = (x_range[1] - x_range[0]) / columns
    xs = x_range[0] + width * (np.arange(columns) + 0.5)
    scans = [{"start": [float(x), float(y), float(z_range[1])], "direction": [0, 0, -1]} for x in xs]
    report = geant4_run(gdml_path, scans=scans, timeout=timeout)
    if "scans" not in report:
        raise RuntimeError(f"Geant4 run failed: {report.get('error')}")

    materials = sorted({seg["material"] for scan in report["scans"] for seg in scan["segments"]})
    colours = dict(zip(materials, plt.cm.tab20.colors))
    fig, ax = plt.subplots(figsize=figsize)
    for x, scan in zip(xs, report["scans"]):
        z = z_range[1]
        for seg in scan["segments"]:
            bottom = max(z - seg["length_mm"], z_range[0])
            ax.bar(x, z - bottom, width, bottom, color=colours[seg["material"]], linewidth=0)
            z = bottom
    ax.legend(handles=[Patch(color=colours[m], label=m) for m in materials],
              loc="upper left", bbox_to_anchor=(1.02, 1))
    ax.set_xlim(*x_range)
    ax.set_ylim(*z_range)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    ax.set_title(title or f"{Path(gdml_path).name}: cross-section at y = {y:g} mm")
    fig.savefig(png_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return report
