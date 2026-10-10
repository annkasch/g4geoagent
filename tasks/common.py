"""Shared helpers for building and checking the hidden reference geometries.

Used only by the tasks' reference scripts, never by the agent.
"""

import math
from pathlib import Path

import pyg4ometry.gdml as gdml
import pyg4ometry.geant4 as g4

from g4geoagent.inspector.geant4_run import geant4_run
from g4geoagent.inspector.render import cross_section

TWO_PI = 2 * math.pi
OVER = 1.0          # mm, how far cutters stick out of the solid they cut
WORLD = ("world_PV", "G4_lAr")

# Germanium enriched to 91% in Ge-76 (atom fraction); the rest is taken as Ge-74.
# Same number of atoms per volume as natural germanium, so the density scales
# with the molar mass.
GE76_FRACTION = 0.91
GE76_MOLAR, GE74_MOLAR = 75.9214, 73.9212               # g/mol
GE_NATURAL_MOLAR, GE_NATURAL_DENSITY = 72.630, 5.323    # g/mol, g/cm3
GE_MOLAR = GE76_FRACTION * GE76_MOLAR + (1 - GE76_FRACTION) * GE74_MOLAR
GE_DENSITY = GE_NATURAL_DENSITY * GE_MOLAR / GE_NATURAL_MOLAR   # 5.551 g/cm3
GE_NAME = "EnrichedGermanium"
CRYSTAL = ("crystal", GE_NAME)


def enriched_germanium(reg):
    ge76 = g4.Isotope("Ge76", 32, 76, GE76_MOLAR, reg)
    ge74 = g4.Isotope("Ge74", 32, 74, GE74_MOLAR, reg)
    element = g4.ElementIsotopeMixture("EnrichedGe", "Ge", 2, reg)
    element.add_isotope(ge76, GE76_FRACTION)
    element.add_isotope(ge74, 1 - GE76_FRACTION)
    material = g4.MaterialCompound(GE_NAME, GE_DENSITY, 1, reg)
    material.add_element_massfraction(element, 1.0)
    return material


def subtract_all(reg, name, solid, cuts):
    """Subtract every (cutter, [rotation, position]) in `cuts` from `solid`."""
    for i, (cutter, transform) in enumerate(cuts):
        step = name if i == len(cuts) - 1 else f"{name}_cut{i}"
        solid = g4.solid.Subtraction(step, solid, cutter, transform, reg)
    return solid


def edge_cuts(reg, radius, height, edge_r):
    """Cutters that round the outer top and bottom edges of a centred cylinder.

    Each cutter is a square ring with the torus that forms the round edge
    taken out of it, so the remaining surface is an exact torus.
    """
    ring = g4.solid.Tubs("edge_ring", radius - edge_r, radius + OVER, edge_r + OVER, 0, TWO_PI, reg)
    torus = g4.solid.Torus("edge_torus", 0, edge_r, radius - edge_r, 0, TWO_PI, reg)
    half = (edge_r + OVER) / 2
    top = g4.solid.Subtraction("top_edge", ring, torus, [[0, 0, 0], [0, 0, -half]], reg)
    bottom = g4.solid.Subtraction("bottom_edge", ring, torus, [[0, 0, 0], [0, 0, half]], reg)
    z = height / 2 - edge_r + half
    return [(top, [[0, 0, 0], [0, 0, z]]), (bottom, [[0, 0, 0], [0, 0, -z]])]


def edge_volume(radius, edge_r):
    """Volume removed by rounding one edge: a square ring minus a quarter-circle ring (Pappus)."""
    r_centre = radius - edge_r
    square = (r_centre + edge_r / 2) * edge_r**2
    quarter = (r_centre + 4 * edge_r / (3 * math.pi)) * math.pi * edge_r**2 / 4
    return 2 * math.pi * (square - quarter)


def write(reg, path):
    writer = gdml.Writer()
    writer.addDetector(reg)
    writer.write(str(path))


def alternate(first, second, lengths, total):
    """Expected scan in which two volumes alternate, starting with `first`.

    `lengths` run up to the last segment of `second`; a final segment of
    `first` fills up to `total`.
    """
    lengths = list(lengths) + [total - sum(lengths)]
    return [((first, second)[i % 2], length) for i, length in enumerate(lengths)]


def check(gdml_path, cases, masses_g, png_path, x_range, z_range, title):
    """Run the reference through Geant4 and compare with hand-calculated values.

    cases     list of (label, scan, expected), expected = [((volume, material), length_mm), ...]
    masses_g  {volume name: mass from the dimensions}
    """
    report = geant4_run(gdml_path, scans=[scan for _, scan, _ in cases])
    assert report["ok"], (report["error"], report["overlaps"], report["problems"][:5])

    worst = 0.0
    for (label, _, expected), scan in zip(cases, report["scans"]):
        found = [((s["volume"], s["material"]), s["length_mm"]) for s in scan["segments"]]
        assert [v for v, _ in found] == [v for v, _ in expected], (label, found, expected)
        error = max(abs(a - b) for (_, a), (_, b) in zip(found, expected))
        assert error < 1e-6, (label, found, expected)
        worst = max(worst, error)
        print(f"ok  {label}")
    print(f"all {len(cases)} line scans agree with the hand calculation, largest difference {worst:.1e} mm")

    # Geant4 estimates the volume of boolean solids by sampling, hence the tolerance.
    parts = {p["volume"]: p for p in report["parts"]}
    for name, mass in masses_g.items():
        found = parts[name]["mass_g"]
        print(f"mass of {name:10s} calculated {mass:9.3f} g, Geant4 estimate {found:9.3f} g")
        assert abs(found / mass - 1) < 0.01, (name, mass, found)

    cross_section(gdml_path, png_path, x_range, z_range, title=title)
    print("PASS  wrote", Path(gdml_path).name, "and", Path(png_path).name)
    return report
