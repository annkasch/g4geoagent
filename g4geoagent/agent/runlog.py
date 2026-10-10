"""Structured log of one run: one JSON object per line, the same format for every detector."""

import json
import time
from pathlib import Path


class RunLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.box = None       # the boxes of the architecture that are at work, set by enter()

    def enter(self, boxes, state="built"):
        """Hand over to `boxes` (names from architecture.yaml). Every later event carries them."""
        self.box = list(boxes)
        self.event("box", "+".join(boxes), state=state)

    def event(self, kind, stage, **fields):
        """Append one event. `kind` is e.g. 'llm_call', 'claim', 'check'; `stage` is the step it belongs to."""
        record = {"time": round(time.time(), 3), "kind": kind, "stage": stage, **fields}
        if self.box:
            record["box"] = self.box
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def events(self, kind=None):
        records = [json.loads(line) for line in self.path.read_text().splitlines()]
        return [r for r in records if kind is None or r["kind"] == kind]
