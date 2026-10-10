"""Smoke test 2: load the GDML from test 1 in Geant4 and check it with geantinos.

A geantino fired down the z axis must cross exactly the layers the geometry
was built with. Also runs Geant4's overlap check and 200 real gammas.

    python smoke/02_geant4.py          needs smoke/out/crystal.gdml from test 1
"""

import json
from pathlib import Path

from g4geoagent.inspector.geant4_run import geant4_run

OUT = Path(__file__).parent / "out"

# Going down from z = +100 mm. Lengths in mm, from the dimensions in test 1.
EXPECTED = [
    ("world_PV", "G4_AIR", 25.0),
    ("endcap", "G4_Al", 1.0),
    ("vacuum", "G4_Galactic", 5.0),
    ("crystal", "G4_Ge", 32.0),
    ("vacuum", "G4_Galactic", 111.0),
    ("endcap", "G4_Al", 1.0),
    ("world_PV", "G4_AIR", 125.0),
]

if __name__ == "__main__":
    down_z = {"start": [0, 0, 100], "direction": [0, 0, -1]}
    gammas = {"particle": "gamma", "energy_MeV": 1.0, "n": 200, **down_z}
    report = geant4_run(OUT / "crystal.gdml", scans=[down_z], real_run=gammas,
                        log_path=OUT / "geant4.log")
    (OUT / "geant4_report.json").write_text(json.dumps(report, indent=1))

    assert report["error"] is None, report
    assert report["loaded"]
    assert report["overlaps"] == [], report["overlaps"]
    assert report["problems"] == [], report["problems"]

    segments = report["scans"][0]["segments"]
    print("line scan down the z axis:")
    for s in segments:
        print(f"  {s['length_mm']:7.2f} mm  {s['volume']:8s} {s['material']}")
    found = [(s["volume"], s["material"], round(s["length_mm"], 6)) for s in segments]
    assert found == EXPECTED, found

    assert [p["volume"] for p in report["parts"]] == ["world_PV", "endcap", "vacuum", "crystal"]
    edep = report["real_run"]["edep_MeV"]
    print("energy deposited by 200 gammas of 1 MeV:",
          {k: round(v, 2) for k, v in edep.items()})
    assert report["real_run"]["completed"] and edep.get("crystal", 0) > 0
    assert report["ok"]
    print("PASS  report in", OUT / "geant4_report.json")
