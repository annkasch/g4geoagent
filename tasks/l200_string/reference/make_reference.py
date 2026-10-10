"""Generate the reference geometry of task l200_string with the public LEGEND-200 package.

Hidden from the agent. Uses legend-pygeom-l200 with its public dummy detector
data, reduced to one detector string. Run it with the package's own environment:

    env_l200/bin/python tasks/l200_string/reference/make_reference.py [string] [detectors]
"""

import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

import yaml

HERE = Path(__file__).parent
STRING = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N_DETECTORS = int(sys.argv[2]) if len(sys.argv) > 2 else 8     # counted from the top of the string
ASSEMBLIES = ["strings", "fibers", "top", "watertank"]          # the cryostat is always built

full = json.loads((resources.files("pygeoml200") / "configs/dummy_geom/channelmap.json").read_text())
keep = {name: ch for name, ch in full.items()
        if ch["system"] != "geds"
        or (ch["location"]["string"] == STRING and ch["location"]["position"] <= N_DETECTORS)}
(HERE / "channelmap_one_string.json").write_text(json.dumps(keep, indent=1))
(HERE / "config.yaml").write_text(yaml.safe_dump(
    {"public_geom": True, "fiber_modules": "segmented", "channelmap": "channelmap_one_string.json",
     "assemblies": ASSEMBLIES}, sort_keys=False))

tool = Path(sys.executable).parent / "legend-pygeom-l200"
subprocess.run([tool, "--config", "config.yaml", "reference.gdml"], cwd=HERE, check=True)
detectors = [name for name, ch in keep.items() if ch["system"] == "geds"]
print(f"wrote reference.gdml: string {STRING} with {len(detectors)} detectors: {', '.join(detectors)}")
