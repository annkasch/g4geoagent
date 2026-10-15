"""Judge a builder's specification for CUORE's Shielding team against the paper and the user's figure.

    python experiments/builder_rounds.py <folder with spec.json and build.json>

Seven checks, each pass or fail, computed from the specification and Geant4's masses (see experiments/notes/builder.md).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from g4geoagent.agent import geometry_spec as GS      # noqa: E402


def shape(spec, part):
    """The volumes of a part as profiles in world z (mm): [(name, [(z, rmin, rmax)], z offset)]."""
    out = []
    for v in spec.volumes:
        if v.part == part:
            prof = GS.profile(spec, v.solid)
            dz = GS._in_mm(v.position[2]) if len(v.position) == 3 else 0.0
            out.append((v.name, [(z + dz, a, b) for z, a, b in prof] if prof else None))
    return out


def radius_at(prof, z):
    """(rmin, rmax) of a profile at height z, interpolated as Geant4 does; None outside it."""
    for (z0, a0, b0), (z1, a1, b1) in zip(prof, prof[1:]):
        if z0 <= z <= z1 and z1 > z0:
            f = (z - z0) / (z1 - z0)
            return a0 + f * (a1 - a0), b0 + f * (b1 - b0)
    return None


def judge(folder):
    folder = Path(folder)
    spec = GS.TeamSpec.model_validate_json((folder / "spec.json").read_text())
    build = json.loads((folder / "build.json").read_text())
    masses = {}
    for v in spec.volumes:
        masses[v.part] = masses.get(v.part, 0) + build["masses_t"].get(v.name, 0)
    checks = {}
    checks["1 no overlaps"] = bool(build["loaded"]) and not build["overlaps"]
    roman = [p for _, p in shape(spec, "roman_lead_shield") if p]
    cup = False
    if len(roman) == 1:
        prof = roman[0]
        zlo, zhi = prof[0][0], prof[-1][0]
        mid = radius_at(prof, (zlo + zhi) / 2)
        low = radius_at(prof, zlo + 10)
        cup = (1700 <= zhi - zlo <= 1850 and mid and 550 <= mid[0] <= 600 and 620 <= mid[1] <= 660
               and low and low[0] == 0 and any(30 <= z - zlo <= 100 and a > 0 for z, a, _ in prof))
    checks["2 Roman Pb is a cup of the stated size"] = bool(cup)
    checks["3 Roman Pb mass within 30% of 5 t"] = 3.5 <= masses.get("roman_lead_shield", 0) <= 6.5
    modern = [p for _, p in shape(spec, "cold_lead_shield") if p]
    slab = False
    if len(modern) == 1:
        prof = modern[0]
        slab = all(a == 0 for _, a, _ in prof) and 250 <= prof[-1][0] - prof[0][0] <= 350 and all(300 <= b <= 500 for _, _, b in prof)
    checks["4 Modern Pb is a solid slab"] = slab
    inside = False
    if len(roman) == 1 and len(modern) == 1:
        r, m = roman[0], modern[0]
        mid = radius_at(r, (m[0][0] + m[-1][0]) / 2)
        inside = r[0][0] + 30 < m[0][0] and m[-1][0] <= r[-1][0] + 1 and mid and max(b for _, _, b in m) <= mid[0] + 1
    checks["5 Modern Pb inside the cup's cavity"] = bool(inside)
    built = {v.part for v in spec.volumes}
    checks["6 polyethylene and boric acid not built in the cryostat"] = not ({"polyethylene_shielding", "boric_acid_panel"} & built)
    text = " ".join(spec.questions + [x.why for x in spec.left_out]).lower()
    checks["7 external shield's facts kept off the Roman shield"] = "external" in text and any(
        k in text for k in ("25 cm", "25cm", "70 t", "70 ton", "k76", "k160", "k159"))
    return checks, masses


if __name__ == "__main__":
    checks, masses = judge(sys.argv[1])
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'fail'}  {k}")
    print(f"  score {sum(checks.values())} of {len(checks)}; masses (t): " + ", ".join(f"{k} {v:.2f}" for k, v in masses.items()))
