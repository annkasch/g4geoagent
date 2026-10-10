"""The architecture as code. architecture.yaml is the specification; this module ties each
step function of the pipeline to its box and checks that a run followed the arrows."""

import functools
from pathlib import Path

import yaml

SPEC = yaml.safe_load((Path(__file__).parent / "architecture.yaml").read_text())
BOXES = SPEC["boxes"]
ARROWS = {(a, b) for a, b, *_ in SPEC["arrows"]}
STEPS = {name for name, box in BOXES.items() if box["kind"] != "data"}
START = "evidence_folder"
FUNCTIONS = {}      # box name: the functions that implement it


def step(*boxes):
    """Mark a function as the implementation of one box, or of boxes that work side by side.

    Its first argument must be the run state. Calling it writes the hand-over to the run log.
    """
    for name in boxes:
        if name not in STEPS:
            raise ValueError(f"{name!r} is not a step in architecture.yaml")

    def wrap(function):
        @functools.wraps(function)
        def run(state, *args, **kwargs):
            states = {BOXES[name]["state"] for name in boxes}
            state.log.enter(boxes, state="stub" if states == {"stub"} else "built")
            return function(state, *args, **kwargs)
        for name in boxes:
            FUNCTIONS.setdefault(name, []).append(run)
        return run
    return wrap


def next_steps(box):
    """The steps `box` may hand over to: along one arrow, or through data boxes."""
    found, seen, todo = set(), set(), [box]
    while todo:
        for a, b in ARROWS:
            if a == todo[-1] and b not in seen:
                seen.add(b)
                (found.add(b) if b in STEPS else todo.insert(0, b))
        todo.pop()
    return found


def check_log(events):
    """What a run did that the architecture does not allow. Returns a list of sentences, empty if all is well."""
    problems, previous = [], [START]
    for event in events:
        if event["kind"] == "box" and event["box"] == previous:
            continue                                    # the same box goes on with its work
        if event["kind"] == "box":
            allowed = set().union(*(next_steps(b) for b in previous))
            for name in event["box"]:
                if name not in allowed:
                    problems.append(f"{' + '.join(previous)} handed over to {name}, but there is no such arrow")
            previous = event["box"]
        elif event["kind"] == "llm_call":
            programs = [b for b in event.get("box") or ["(no box)"] if BOXES.get(b, {}).get("kind") != "ai"]
            if programs:
                problems.append(f"a model was called in {' + '.join(programs)} (stage {event['stage']}), which is not an AI step")
    return sorted(set(problems))
