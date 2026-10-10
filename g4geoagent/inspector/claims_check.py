"""Measure a built geometry against the claims it was built from. A program, no LLM.

The builder says which volume shows which claim (`shown`: claim id, volume name,
what to measure). This module takes the expected number from the claim itself,
measures the volume in Geant4's report and compares the two.
"""

from g4geoagent.agent.compare import claim_numbers

LENGTH = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "km": 1e6, "um": 1e-3, "µm": 1e-3, "μm": 1e-3, "nm": 1e-6, "inch": 25.4}
MASS = {"g": 1.0, "kg": 1e3, "t": 1e6, "ton": 1e6, "tons": 1e6, "tonne": 1e6, "tonnes": 1e6, "kt": 1e9, "kton": 1e9, "mg": 1e-3}
VOLUME = {"cm3": 1.0, "m3": 1e6, "mm3": 1e-3, "l": 1e3, "liter": 1e3, "litre": 1e3, "liters": 1e3, "litres": 1e3}
# what can be measured: (units it accepts, relative tolerance)
MEASURES = {"size_x": (LENGTH, 0.01), "size_y": (LENGTH, 0.01), "size_z": (LENGTH, 0.01),
            "mass": (MASS, 0.10), "volume": (VOLUME, 0.10), "count": (None, 0.0)}


def _unit(text):
    return text.strip().lower().replace("³", "3").replace("^3", "3").replace(" ", "").rstrip(".")


def _measure(volumes, measure):
    """The measured number for `measure` on the placed volumes of one name."""
    if measure == "count":
        return float(len(volumes))
    if measure == "mass":
        return sum(v["mass_g"] for v in volumes)
    if measure == "volume":
        return sum(v["solid_volume_cm3"] for v in volumes)
    return volumes[0]["size_mm"]["xyz".index(measure[-1])]


def check_claims(claims, shown, report):
    """Compare each claim with the geometry.

    claims  {id: Claim}, the claims that describe what is built
    shown   list of {"id", "volume", "measure"} from the builder
    report  Geant4's report of the build (geant4_run)

    Returns one row per claim: {"id", "status", "expected", "measured", "unit", "volume", "measure", "why"}.
    status: "met", "not met", "not measurable" (the builder named a volume, but no number can be
    compared) or "not shown" (the builder named no volume for this claim).
    """
    parts = report.get("parts", [])
    rows, by_id = [], {}
    for entry in shown:
        by_id.setdefault(str(entry.get("id")), entry)
    for key, claim in claims.items():
        row = {"id": key, "status": "not shown", "expected": None, "measured": None, "unit": "",
               "volume": "", "measure": "", "why": ""}
        rows.append(row)
        entry = by_id.get(key)
        if entry is None:
            continue
        volume, measure = str(entry.get("volume", "")), str(entry.get("measure", ""))
        row.update(status="not measurable", volume=volume, measure=measure)
        if measure not in MEASURES:
            row["why"] = f"'{measure}' is not one of {', '.join(MEASURES)}"
            continue
        units, tolerance = MEASURES[measure]
        numbers = claim_numbers(claim)
        if len(numbers) != 1:
            row["why"] = "the claim does not state exactly one number"
            continue
        if units is None:
            expected, row["unit"] = numbers[0], ""
        elif _unit(claim.unit) in units:
            expected = numbers[0] * units[_unit(claim.unit)]
            row["unit"] = {id(LENGTH): "mm", id(MASS): "g", id(VOLUME): "cm3"}[id(units)]
        else:
            row["why"] = f"the unit '{claim.unit}' does not fit '{measure}'"
            continue
        exact = [p for p in parts if p["volume"] == volume]
        prefix = [p for p in parts if p["volume"].startswith(volume)]
        # a count covers every placed volume whose name starts with the given name ("pmt" for pmt_0, pmt_1, ...)
        volumes = prefix if measure == "count" else exact or prefix
        if not volumes:
            row.update(status="not met", expected=expected, why=f"there is no volume named '{volume}'")
            continue
        measured = _measure(volumes, measure)
        met = abs(measured - expected) <= tolerance * abs(expected) + 1e-9
        row.update(status="met" if met else "not met", expected=expected, measured=measured)
    return rows


def summary(rows):
    counts = {status: sum(r["status"] == status for r in rows) for status in ("met", "not met", "not measurable", "not shown")}
    return {**counts, "claims": len(rows)}


def as_feedback(rows, claims):
    """The rows that are not met, as text for the builder. Empty if there are none."""
    lines = []
    for row in rows:
        if row["status"] != "not met":
            continue
        claim = claims[row["id"]]
        stated = f"{claim.part} {claim.quantity} = {claim.value} {claim.unit}".strip()
        if row["measured"] is None:
            lines.append(f"- {row['id']} ({stated}): {row['why']}")
        else:
            lines.append(f"- {row['id']} ({stated}): {row['measure']} of '{row['volume']}' should be "
                         f"{row['expected']:g} {row['unit']}, but is {row['measured']:g} {row['unit']}")
    return "\n".join(lines)
