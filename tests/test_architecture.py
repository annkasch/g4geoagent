"""Do the code and the runs follow architecture.yaml?

    python tests/test_architecture.py [run folder ...]

Without arguments: checks the code. With run folders: also checks each run's log.
"""

import json
import subprocess
import sys
from pathlib import Path

import g4geoagent.pipeline  # noqa: F401  (registers the step functions)
from g4geoagent.architecture import ARROWS, BOXES, FUNCTIONS, STEPS, check_log

ROOT = Path(__file__).parents[1]


def test_every_step_has_a_function():
    assert STEPS == set(FUNCTIONS), f"steps without a function: {sorted(STEPS - set(FUNCTIONS))}"


def test_boxes_are_complete():
    for name, box in BOXES.items():
        assert box["kind"] in ("ai", "program", "data"), name
        if box["kind"] != "data":
            assert box.get("state") in ("built", "stub"), f"{name} has no state"
            assert box.get("first") and box.get("done"), f"{name} lacks its first-version scope"


def test_arrows_join_known_boxes():
    for a, b in ARROWS:
        assert a in BOXES and b in BOXES, (a, b)


def test_pipeline_calls_only_steps():
    """Every function that the run calls with the state is a box, or a helper that chains boxes."""
    source = (ROOT / "g4geoagent" / "pipeline.py").read_text()
    body = source[source.index("def build_round("):source.index("def construction_figures_step(")]
    import re
    called = set(re.findall(r"(?<![.\w])([a-z_]+)\(state[,)]", body)) - {"build_round", "run"}
    steps = {f.__name__ for functions in FUNCTIONS.values() for f in functions}
    helpers = {"read_documents", "build_round", "construction_figures_step", "pieces"}     # they only chain boxes
    assert called <= steps | helpers, f"not a box: {sorted(called - steps - helpers)}"


def test_drawing_matches():
    """The drawing script fails if it shows other boxes or arrows than architecture.yaml."""
    done = subprocess.run([sys.executable, str(ROOT / "diagrams" / "architecture.py")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-500:]


def check_run(folder):
    events = [json.loads(line) for line in (Path(folder) / "log.jsonl").read_text().splitlines()]
    return check_log(events)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok  ", name)
    for folder in sys.argv[1:]:
        problems = check_run(folder)
        print("ok  " if not problems else "FAIL", folder, *problems, sep="\n     " if problems else " ")
