"""Measure how a built geometry differs from the reference. A program, no LLM.

Both GDML files are loaded in Geant4 and crossed by the same straight lines.
Along each line the material of the build is compared with the material of the
reference. Materials are compared by density, not by name, because the builder
chooses its own names.

Runs outside the agent's sandbox, on finished builds only.
"""

import random

from g4geoagent.inspector.geant4_run import geant4_run

DENSITY_TOLERANCE = 0.02      # relative: densities closer than this count as the same material
LINE_TOLERANCE = 0.05         # mm of differing material that a line may have and still count as matching


def lines(region, per_axis, seed=0):
    """Straight lines through the box `region` ([[x0, x1], [y0, y1], [z0, z1]] in mm), parallel to the axes.

    Returns (scans for geant4_run, length of each line inside the region).
    """
    rng = random.Random(seed)
    scans, lengths = [], []
    for axis in range(3):
        for _ in range(per_axis):
            start = [rng.uniform(lo, hi) for lo, hi in region]
            start[axis] = region[axis][1]
            direction = [0.0, 0.0, 0.0]
            direction[axis] = -1.0
            scans.append({"start": start, "direction": direction})
            lengths.append(region[axis][1] - region[axis][0])
    return scans, lengths


def _profile(report, scan_index, length):
    """Material along one line as [(end position, density, material name)], cut at `length`."""
    density = {p["material"]: p["density_g_cm3"] for p in report["parts"]}
    profile, position = [], 0.0
    for segment in report["scans"][scan_index]["segments"]:
        position = min(position + segment["length_mm"], length)
        profile.append((position, density[segment["material"]], segment["material"]))
        if position >= length:
            break
    if not profile or profile[-1][0] < length:      # the line left the world early
        profile.append((length, 0.0, "outside the world"))
    return profile


def _same(a, b):
    return abs(a - b) <= DENSITY_TOLERANCE * max(a, b, 1e-12)


def measure(build_gdml, reference_gdml, region, per_axis=400, seed=0):
    """Compare a build with the reference inside `region`.

    Returns a dict with:
      valid          the build loads in Geant4 without overlaps or warnings
      agreement      share of the non-surrounding material, in build or reference, where both agree (0 to 1)
      lines_matching share of the lines on which build and reference are the same everywhere. Small
                     features (a groove, a rounded edge) hardly change `agreement` but do change this
      differences    the largest differences found: where, and which material each side has there
      materials      per reference material: share of it that the build has in the right place
      extra          share of the region where the build has material and the reference has only the surroundings
      mass           total mass without the surroundings: build, reference, relative difference
      problems       what Geant4 complained about in the build
    """
    scans, lengths = lines(region, per_axis, seed)
    reference = geant4_run(reference_gdml, scans=scans)
    if not reference["ok"]:
        raise RuntimeError(f"the reference itself is not valid: {reference['error']} {reference['problems'][:3]}")
    build = geant4_run(build_gdml, scans=scans)
    result = {"valid": build["ok"], "loaded": build["loaded"], "overlaps": build["overlaps"],
              "problems": build["problems"][:10], "error": build["error"]}
    if "scans" not in build or len(build["scans"]) != len(scans):
        return {**result, "agreement": 0.0, "lines_matching": 0.0, "differences": [], "materials": {},
                "extra": None, "mass": None}

    surroundings = reference["parts"][0]["density_g_cm3"]          # the reference's world material
    per_material, either, both, extra, total = {}, 0.0, 0.0, 0.0, 0.0
    matching, differences = 0, []
    for i, length in enumerate(lengths):
        a, b = _profile(build, i, length), _profile(reference, i, length)
        position, ia, ib, differing = 0.0, 0, 0, 0.0
        while position < length - 1e-9:
            end = min(a[ia][0], b[ib][0])
            piece = end - position
            in_build, in_reference = a[ia][1], b[ib][1]
            solid_build = not _same(in_build, surroundings)
            solid_reference = not _same(in_reference, surroundings)
            total += piece
            if not _same(in_build, in_reference):
                differing += piece
                start, direction = scans[i]["start"], scans[i]["direction"]
                middle = [round(start[k] + direction[k] * (position + piece / 2), 2) for k in range(3)]
                differences.append({"length_mm": round(piece, 3), "at_mm": middle,
                                    "build": a[ia][2], "reference": b[ib][2]})
            if solid_reference:
                entry = per_material.setdefault(b[ib][2], [0.0, 0.0])
                entry[0] += piece
                entry[1] += piece if _same(in_build, in_reference) else 0.0
            if solid_build or solid_reference:
                either += piece
                both += piece if _same(in_build, in_reference) else 0.0
            if solid_build and not solid_reference:
                extra += piece
            position = end
            ia += a[ia][0] <= end + 1e-12
            ib += b[ib][0] <= end + 1e-12
            ia, ib = min(ia, len(a) - 1), min(ib, len(b) - 1)
        matching += differing < LINE_TOLERANCE

    def solid_mass(report):
        return sum(p["mass_g"] for p in report["parts"][1:] if not _same(p["density_g_cm3"], surroundings))

    mass_build, mass_reference = solid_mass(build), solid_mass(reference)
    return {**result,
            "agreement": both / either if either else 1.0,
            "lines_matching": matching / len(lengths),
            "differences": sorted(differences, key=lambda d: -d["length_mm"])[:20],
            "materials": {name: right / length for name, (length, right) in per_material.items()},
            "extra": extra / total,
            "mass": {"build_g": mass_build, "reference_g": mass_reference,
                     "difference": (mass_build - mass_reference) / mass_reference if mass_reference else None}}
