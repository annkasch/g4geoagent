# LEGEND-200 detector string: arrangement key for grading

From legend-pygeom-l200 (../reference_code, src/pygeoml200/hpge_strings.py and configs/extra_meta, p15).
Used ONLY to grade a build of one string. Never shown to the system. Points are arrangement, not part lists.

| # | Check | Reference |
|---|---|---|
| A1 | Strings in the array | 12, on two radii: 218 mm (angles 0, 30, 60, 180, 210, 240) and 222 mm (the rest) |
| A2 | Detectors per string | several units stacked vertically, top unit hangs from the support at the top plate |
| A3 | Unit pitch | one copper rod segment per unit, 124-131 mm (cold length = warm x 0.997) |
| A4 | Rods | 3 copper rods per string, 120 deg apart, at r 39.5-49.5 mm from the string axis, radius 1.5 mm |
| A5 | Order within a unit, bottom to top | Ultem clamp (3.7) -> copper weldment flap (1.5) -> PEN base plate (1.5) -> Ultem insulators (2.4) -> detector |
| A6 | Detector orientation | detector sits ON the PEN plate, contact side down; PPC types also get a top PEN ring |
| A7 | Front end | LMFE and signal clamp under the PEN plate, off-axis; HV clamp on the opposite side |
| A8 | Cables | signal and HV cables (0.076 mm) run up the string as bundles, one per detector below |
| A9 | Top of string | copper hanger and tristar 12 mm above the top unit, under the top plate |
| A10 | Minishroud | nylon tube around each string, r 44-54 mm, 0.125 mm wall, ~1000 mm long (some shorter), lid on top |
| A11 | Electronics | HV boards and CC4 boards below the top plate, between strings |

Ref sources inside the code: offsets "from CAD model", some "estimate", minishroud from an email.
