"""Does the measuring program notice known errors? Builds broken copies of the BEGe
reference and measures each against the true reference.

    python experiments/measure_validation.py
"""

import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "tasks"), str(ROOT / "tasks/bege/reference")]
import build_reference as ref   # noqa: E402
import common                   # noqa: E402

from g4geoagent.evaluator.measure import measure   # noqa: E402

REFERENCE = ROOT / "tasks/bege/reference/reference.gdml"
REGION = yaml.safe_load((ROOT / "tasks/bege/meta.yaml").read_text())["evaluate"]["region_mm"]


def broken(change, text_edit=None):
    """GDML of the reference with one constant changed, or with its text edited."""
    saved = {(module, name): getattr(module, name) for module, name, _ in change}
    for module, name, value in change:
        setattr(module, name, value)
    path = Path(tempfile.mkdtemp()) / "build.gdml"
    common.write(ref.build(), path)
    for (module, name), value in saved.items():
        setattr(module, name, value)
    if text_edit:
        path.write_text(path.read_text().replace(*text_edit))
    return path


CASES = [
    ("identical copy", [], None),
    ("height halved (half-length error)", [(ref, "HEIGHT", 20.0)], None),
    ("radius used as diameter", [(ref, "RADIUS", 17.95)], None),
    ("crystal centred on the origin", [], ('z="20.000000000000000"', 'z="0.0"')),
    ("crystal shifted 5 mm sideways", [], ('x="0.000000000000000" y="0.000000000000000" z="20.000000000000000"',
                                           'x="5.0" y="0.0" z="20.000000000000000"')),
    ("groove left out", [(ref, "GROOVE_DEPTH", 0.001)], None),
    ("groove twice as deep", [(ref, "GROOVE_DEPTH", 4.0)], None),
    ("edges not rounded", [(ref, "EDGE_R", 0.01)], None),
    ("natural instead of enriched germanium", [(common, "GE_DENSITY", 5.323)], None),
]

if __name__ == "__main__":
    print(f"{'case':40s} valid  agreement  lines matching  extra   mass difference")
    for label, change, text_edit in CASES:
        r = measure(broken(change, text_edit), REFERENCE, REGION)
        mass = f"{r['mass']['difference']:+7.1%}" if r["mass"] else "   -"
        print(f"{label:40s} {str(r['valid']):5s}  {r['agreement']:8.1%}  {r['lines_matching']:13.1%}  {r['extra']:6.2%}  {mass}")
