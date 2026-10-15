"""Score figure layouts against the hand layouts in experiments/layout_gold.

    python experiments/layout_bench.py <folder with <figure>.json>

Per figure: parts found (a reader part whose label or description matches the hand part's names, each reader part
used once), containment right (the found part sits inside the found part of its hand parent, directly or deeper),
shapes right, and the reader's extra parts.
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field                  # noqa: E402

from g4geoagent.agent.figure_layout import Layout      # noqa: E402
from g4geoagent.agent.llm import call_llm_json         # noqa: E402

GOLD = ROOT / "experiments/layout_gold"
NEAR = {"vessel": {"cup", "cylinder", "tube"}, "cylinder": {"vessel", "tube"}, "tube": {"cylinder", "ring"},
        "plate": {"cylinder"}, "ring": {"tube"}, "cup": {"vessel"}}       # forms close enough to count


class Pair(BaseModel):
    hand: str
    reader: str = Field(description="the reader's part id, or 'none'")


class Pairs(BaseModel):
    pairs: list[Pair]


def pair(layout, gold, log=None):
    """A text model pairs each hand part with the reader part that is the same thing (by label, description, place)."""
    hand = "\n".join(f"  {g['id']}: {g.get('what', g['names'])} ({g['shape']}, inside {g['inside']})" for g in gold["parts"])
    read = "\n".join(f"  {p.id}: label '{p.label}'; {p.description} ({p.shape}, inside {p.inside}, {p.where})" for p in layout.parts)
    request = (f"Two descriptions of the parts in one figure of {gold['detector']}: one written by hand, one by a reader. "
               "Pair each hand part with the reader part that is the same physical thing, judged by label, description and "
               "place; 'none' if the reader has no such part. Each reader part at most once.\n\nHand parts:\n" + hand
               + "\n\nReader parts:\n" + read + '\n\nAnswer with one JSON object: {"pairs": [{"hand": "...", "reader": "p1"}, ...]}')
    answer, _ = call_llm_json("lbl/gpt-oss-120b", [{"role": "user", "content": request}], Pairs, log=log, stage="layout_judge", temperature=0)
    known = {p.id for p in layout.parts}
    match, used = {}, set()
    for x in answer.pairs:
        if x.reader in known and x.reader not in used and x.hand in {g["id"] for g in gold["parts"]}:
            match[x.hand] = x.reader
            used.add(x.reader)
    return match


def score(layout, gold, match):
    parts = list(layout.parts)
    inside = {p.id: p.inside for p in parts}

    def within(child, parent):
        seen, at = set(), inside.get(child)
        while at and at != "none" and at not in seen:
            if at == parent:
                return True
            seen.add(at)
            at = inside.get(at)
        return False
    by_id = {p.id: p for p in parts}
    nested = [g for g in gold["parts"] if g["inside"] != "none"]
    parents = lambda g: g["inside"] if isinstance(g["inside"], list) else [g["inside"]]
    right = [g for g in nested if g["id"] in match and any(q in match and within(match[g["id"]], match[q]) for q in parents(g))]
    shapes = [g for g in gold["parts"] if g["id"] in match and (by_id[match[g["id"]]].shape == g["shape"]
                                                                 or by_id[match[g["id"]]].shape in NEAR.get(g["shape"], ()))]
    return {"found": len(match), "parts": len(gold["parts"]), "nested_right": len(right), "nested": len(nested),
            "shapes_right": len(shapes), "extra": len(parts) - len(match),
            "missed": [g["id"] for g in gold["parts"] if g["id"] not in match],
            "wrong_nesting": [g["id"] for g in nested if g["id"] in match and g not in right]}


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    total = {"found": 0, "parts": 0, "nested_right": 0, "nested": 0, "shapes_right": 0}
    for gold_file in sorted(GOLD.glob("*.yaml")):
        reading = folder / f"{gold_file.stem}.json"
        if not reading.exists():
            print(f"{gold_file.stem:40s} no reading")
            continue
        layout, gold = Layout.model_validate_json(reading.read_text()), yaml.safe_load(gold_file.read_text())
        cache = folder / f"{gold_file.stem}.pairs.json"
        match = json.loads(cache.read_text()) if cache.exists() else pair(layout, gold)
        cache.write_text(json.dumps(match, indent=1))
        r = score(layout, gold, match)
        for k in total:
            total[k] += r[k]
        print(f"{gold_file.stem[:40]:40s} parts {r['found']}/{r['parts']}  nesting {r['nested_right']}/{r['nested']}  "
              f"shapes {r['shapes_right']}/{r['parts']}  extra {r['extra']}  missed {r['missed']}  wrong nesting {r['wrong_nesting']}")
    print(f"{'TOTAL':40s} parts {total['found']}/{total['parts']}  nesting {total['nested_right']}/{total['nested']}  "
          f"shapes {total['shapes_right']}/{total['parts']}")
