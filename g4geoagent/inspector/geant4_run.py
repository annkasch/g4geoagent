"""Geant4 test run: load a GDML file, check overlaps, scan with geantinos, short real run.

Shared by the Inspector and the Evaluator. Geant4 runs in a separate process,
so a crash or hang on a bad geometry comes back as a failed report.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Lines in Geant4's output that mean something went wrong.
_PROBLEM = re.compile(r"G4Exception|WARNING|ERROR|stuck", re.IGNORECASE)


_OVERLAP = re.compile(r"Overlap is detected for volume (\S+?)(?::\d+)? \((\w+)\)\s+with (its mother volume )?(\S+?)(?::\d+)? \((\w+)\)"
                      r"\s+(?:protrusion|overlapping)?[^\n]*? by ([\d.eE+-]+ \w+)")
_ENCLOSING = re.compile(r"Overlap is detected for volume (\S+?)(?::\d+)? \((\w+)\)\s+apparently fully encapsulating "
                        r"volume (\S+?)(?::\d+)? \((\w+)\)")


def overlap_details(log, sizes=None, places=None):
    """Geant4's overlap messages, each pair of volumes once: "a (G4Box) sticks out of its mother b (G4Tubs) by 1 cm".
    With `sizes` ({volume: "x x y x z"} in mm) the full sizes of both are added, so that one sees which is too large."""
    found, sizes, places = {}, sizes or {}, places or {}

    def size(volume):
        known = sizes.get(volume) or next((s for name, s in sizes.items() if name.startswith(volume)), "")
        return f", full size {known} mm" if known else ""
    for volume, solid, other, other_solid in _ENCLOSING.findall(log):
        found.setdefault((volume.rstrip("0123456789"), other.rstrip("0123456789"), "in"),
                         f"{volume} ({solid}) completely encloses {other} ({other_solid}), which is placed in the same "
                         f"mother: place {other} inside {volume}, or move it out")
    for volume, solid, mother, other, other_solid, amount in _OVERLAP.findall(log):
        text = (f"{volume} ({solid}{size(volume)}) sticks out of its mother {other} ({other_solid}{size(other)}) by up to {amount}"
                + (f"; its centre is placed at ({places[volume]}) mm from the mother's centre" if volume in places else "")
                if mother else f"{volume} ({solid}{size(volume)}) overlaps {other} ({other_solid}{size(other)}) by up to {amount}")
        found.setdefault((volume.rstrip("0123456789"), other.rstrip("0123456789"), bool(mother)), text)
    return list(found.values())


def geant4_run(gdml_path, scans=None, real_run=None, timeout=600, log_path=None):
    """Run the Geant4 checks on `gdml_path` and return a report dict.

    scans     list of {"start": [x, y, z], "direction": [dx, dy, dz]} in mm, in
              world coordinates. Default: one line along each axis.
    real_run  {"particle", "energy_MeV", "n", "start", "direction"} or None.
    log_path  where to keep Geant4's full output (optional).

    Report keys: ok, loaded, parts, overlaps, scans, real_run, problems, error.
    `ok` is True when the file loaded, nothing overlaps and Geant4 printed
    no warnings or errors.
    """
    gdml_path = Path(gdml_path).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        request_file = Path(tmp) / "request.json"
        result_file = Path(tmp) / "result.json"
        request_file.write_text(json.dumps(
            {"gdml": str(gdml_path), "scans": scans, "real_run": real_run}))
        command = [sys.executable, "-m", "g4geoagent.inspector._geant4_worker",
                   str(request_file), str(result_file)]
        error = None
        try:
            process = subprocess.run(command, capture_output=True, text=True,
                                     timeout=timeout)
            log = process.stdout + process.stderr
            if process.returncode != 0:
                error = f"Geant4 process exited with code {process.returncode}"
        except subprocess.TimeoutExpired as expired:
            log = (expired.stdout or b"").decode(errors="replace")
            error = f"Geant4 process timed out after {timeout} s"
        report = json.loads(result_file.read_text()) if result_file.exists() else {}

    if log_path:
        Path(log_path).write_text(log)
    report.setdefault("loaded", False)
    report.setdefault("overlaps", [])
    report["problems"] = [line.strip() for line in log.splitlines()
                          if _PROBLEM.search(line)]
    sizes, places = {}, {}
    for part in report.get("parts", []):
        places.setdefault(part["volume"], ", ".join(f"{x:.0f}" for x in part["position_mm"]))
        for name in (part["volume"], part.get("logical", "")):       # a mother is reported by its logical name
            sizes.setdefault(name, " x ".join(f"{s:.0f}" for s in part.get("size_mm", [])))
    report["overlap_details"] = overlap_details(log, sizes, places)
    report["error"] = error
    if error:
        report["log_tail"] = log.splitlines()[-30:]
    report["ok"] = (error is None and report["loaded"]
                    and not report["overlaps"] and not report["problems"])
    return report
