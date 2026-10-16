"""Public geometry code must not reach the agent: it is only for grading.

    python tests/test_leak.py [run folder ...]

1. The agent cannot fetch from code hosts or fetch code files, also through a redirect.
2. No agent module imports the Evaluator, and no agent code or prompt names the reference code folder.
3. With run folders: no file in a run's evidence folder came from a code host, and none holds a distinctive
   line of a reference repository in ../reference_code/ (volume names and the like, at least 20 characters).
"""

import json
import re
import sys
from pathlib import Path

from g4geoagent.agent.evidence import is_allowed

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT.parent / "reference_code"
AGENT = [ROOT / "g4geoagent" / d for d in ("agent", "blueprint", "reviewer", "inspector")]


def test_code_hosts_refused():
    for url in ["https://github.com/legend-exp/legend-pygeom-l200",
                "https://raw.githubusercontent.com/legend-exp/legend-pygeom-l200/HEAD/src/pygeoml200/cryo.py",
                "https://legend-pygeom-l200.readthedocs.io/en/stable/description.html",
                "https://gitlab.cern.ch/some/geometry", "https://pypi.org/project/pygeoml200/",
                "https://arxiv.org/src/2501.00001/geometry.gdml"]:
        assert not is_allowed(url), url
    assert is_allowed("https://arxiv.org/pdf/2104.02565")


def test_agent_does_not_see_the_evaluator():
    for folder in AGENT:
        for file in folder.rglob("*"):
            if file.suffix not in (".py", ".md") or not file.is_file():
                continue
            text = file.read_text(errors="ignore")
            assert not re.search(r"(from|import)\s+g4geoagent\.evaluator", text), file
            assert "reference_code" not in text, file


def reference_lines():
    """Distinctive string literals of the reference repositories: names of volumes, files and so on."""
    found = set()
    for file in REFERENCE.rglob("*.py") if REFERENCE.exists() else []:
        for literal in re.findall(r"[\"']([A-Za-z0-9_{}.\-]{20,})[\"']", file.read_text(errors="ignore")):
            if "_" in literal and not literal.startswith(("http", "pygeom")):
                found.add(literal.split("{")[0])
    return {line for line in found if len(line) >= 20}


def check_run(folder):
    evidence = Path(folder) / "evidence"
    problems = []
    for line in (evidence / "sources.jsonl").read_text().splitlines() if (evidence / "sources.jsonl").exists() else []:
        entry = json.loads(line)
        if entry.get("url") and not is_allowed(entry["url"]):
            problems.append(f"{entry['file']} came from {entry['url']}")
    lines = reference_lines()
    for file in evidence.rglob("*.txt") if evidence.exists() else []:
        text = file.read_text(errors="ignore")
        hits = sorted(line for line in lines if line in text)
        if hits:
            problems.append(f"{file.name} holds lines of reference code: {hits[:3]}")
    return problems


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok  ", name)
    print(f"reference lines watched: {len(reference_lines())}")
    for folder in sys.argv[1:]:
        problems = check_run(folder)
        print("ok  " if not problems else "FAIL", folder, *problems, sep="\n     " if problems else " ")
