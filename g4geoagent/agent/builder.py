"""The building step: from a specification to a GDML file, with the agent's own checks.

One attempt is: the model writes the geometry, a program runs it and loads the
result in Geant4, and what went wrong goes back to the model. The builder never
sees a reference geometry.

Two ways of writing (`style`):
  "pyg4ometry"  a Python script that writes the GDML file
  "gdml"        the GDML file directly

Two kinds of feedback (`feedback`):
  "errors"   only failures: the script crashed, Geant4 could not load the file, parts overlap
  "measure"  also, once the file is valid, what Geant4 measures in it (parts, masses, line scans),
             so that the model can compare its build with the specification
"""

import re
import subprocess
import sys
from pathlib import Path

from g4geoagent.agent.llm import call_llm
from g4geoagent.inspector.geant4_run import geant4_run

PROMPTS = Path(__file__).parent / "prompts"
BLOCK = {"pyg4ometry": "python", "gdml": "xml"}
SCRIPT_TIMEOUT = 180      # seconds


def _code(text, language):
    """The last fenced block of an answer."""
    blocks = re.findall(r"```(?:%s|\w*)\n(.*?)```" % language, text, flags=re.DOTALL)
    return blocks[-1] if blocks else None


def _run_script(script, gdml):
    """Run a generated script in its own process. Returns an error text, or None."""
    try:
        done = subprocess.run([sys.executable, "-I", script.name, gdml.name], cwd=script.parent,
                              capture_output=True, text=True, timeout=SCRIPT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"The script did not finish within {SCRIPT_TIMEOUT} s."
    if done.returncode != 0:
        return "The script failed:\n" + "\n".join((done.stderr or done.stdout).splitlines()[-25:])
    if not gdml.exists():
        return "The script ran but did not write the GDML file to sys.argv[1]."
    return None


def _describe(report):
    """What Geant4 measures in a valid geometry, as text for the model."""
    lines = ["Volumes (name, inside, material, density g/cm3, mass g, position of its origin in the mother in mm):"]
    for p in report["parts"]:
        position = ", ".join(f"{v:.3f}" for v in p["position_mm"])
        lines.append(f"  {p['volume']}, {p['mother']}, {p['material']}, {p['density_g_cm3']:.4g}, "
                     f"{p['mass_g']:.4g}, ({position})")
    lines.append("Materials crossed by straight lines, each starting just inside the world boundary:")
    for scan in report["scans"]:
        axis = "xyz"[[abs(d) for d in scan["direction"]].index(1.0)]
        start = ", ".join(f"{v:.1f}" for v in scan["start"])
        path = "; ".join(f"{s['length_mm']:.3f} mm {s['material']}" for s in scan["segments"])
        lines.append(f"  from ({start}) towards -{axis}: {path}")
    return "\n".join(lines)


def build(specification, model, workdir, style="pyg4ometry", feedback="errors", attempts=5,
          log=None, seed=None):
    """Build a geometry for `specification` (text). Returns a dict:

    gdml       path of the last valid GDML file, or None
    valid      whether that file loads in Geant4 without overlaps or warnings
    attempts   number of answers the model gave
    finished   why the loop ended: "valid", "model says done" or "out of attempts"
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    stage = f"builder_{style}_{feedback}"
    options = {"temperature": 0} | ({"seed": seed} if seed is not None else {})
    messages = [{"role": "system", "content": (PROMPTS / f"builder_{style}.md").read_text()},
                {"role": "user", "content": "Specification:\n\n" + specification}]
    best = None

    def event(**fields):
        if log:
            log.event("build_attempt", stage, model=model, **fields)

    for attempt in range(1, attempts + 1):
        answer = call_llm(model, messages, log=log, stage=stage, **options)["text"]
        messages.append({"role": "assistant", "content": answer})
        if best and re.search(r"\bDONE\b", answer) and not _code(answer, BLOCK[style]):
            event(attempt=attempt, outcome="model says done")
            return {"gdml": best, "valid": True, "attempts": attempt, "finished": "model says done"}

        code = _code(answer, BLOCK[style])
        gdml = workdir / f"attempt{attempt}.gdml"
        if code is None:
            problem = f"There was no ```{BLOCK[style]} block in your answer."
        elif style == "gdml":
            gdml.write_text(code)
            problem = None
        else:
            script = workdir / f"attempt{attempt}.py"
            script.write_text(code)
            problem = _run_script(script, gdml)

        report = None
        if problem is None:
            report = geant4_run(gdml, timeout=300)
            if not report["ok"]:
                # after a crash the last lines of Geant4's output hold the full error message
                output = [line for line in report.get("log_tail", []) if line.strip()] or report["problems"][:12]
                details = [report["error"] or "", *(f"overlap: {v}" for v in report["overlaps"]), *output]
                problem = ("Geant4 could not load the file.\n" if not report["loaded"]
                           else "Geant4 reports problems with the geometry.\n") + "\n".join(d for d in details if d)

        if problem:
            event(attempt=attempt, outcome="problem", problem=problem[:400])
            messages.append({"role": "user", "content": problem + "\n\nSend the corrected complete answer."})
            continue

        best = gdml
        if feedback == "errors":
            event(attempt=attempt, outcome="valid")
            return {"gdml": best, "valid": True, "attempts": attempt, "finished": "valid"}
        event(attempt=attempt, outcome="valid, measurements sent")
        messages.append({"role": "user", "content":
                         "The file loads in Geant4 without overlaps. This is what Geant4 measures in it:\n\n"
                         + _describe(report) + "\n\nCompare this with the specification: every dimension, position, "
                         "material and mass that the specification lets you check. If everything matches, answer "
                         "with the single word DONE. Otherwise send the corrected complete answer."})

    return {"gdml": best, "valid": best is not None, "attempts": attempts, "finished": "out of attempts"}
