"""Step 2 of the string test: text reader and picture reader work together on one LEGEND-200 string.

    python experiments/ceiling/string_together.py <seed>

1. text reader (gpt-oss) lists the string's parts from the paper's words: name, material, what the text says about place;
2. picture reader (gemma-4), per picture, gets that list and says for each part: seen or not, where, on/under/around
   what, how many, size as a ratio to the detector; plus things it sees that the list does not name;
3. text reader merges: where pictures agree, where they disagree, and the questions for the next round: for the
   pictures (is X there?) and for the text (what is the unnamed copper tab?).
Answers go to runs/ceiling/string_together/s<seed>/.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))

from g4geoagent.agent.llm import call_llm, image_message   # noqa: E402

TEXT = ROOT / "runs/papers_test/text/legend.txt"
PICTURES = {
    "string_photo": "a photo of one detector string being assembled in a glove box",
    "unit_render": "a rendering of one detector unit of the string",
    "unit_photo_pen_plate": "a close-up photo of one detector unit, seen from below",
    "array_render": "a rendering of the whole detector array",
}

TEXT_PROMPT = """From this passage of a LEGEND-200 paper, list every part of a germanium detector string and of the \
array of strings: name as the text gives it, material, count, and every word the text says about where it is or what \
it is attached to. Quote the words. Add nothing the passage does not say.

PASSAGE:
{passage}"""

PICTURE_PROMPT = """This is {what} of the LEGEND-200 germanium detector array. The paper names these parts:

{parts}

For EACH named part say, only from what you SEE in the picture:
- seen / not seen / unsure, and which visible thing it is (colour, shape);
- where it is: on, under, above, around, clamped to which other part;
- how many, and how spread (angles around the axis, in a column);
- size as a ratio to the germanium detector (e.g. 'thickness ~1/20 of detector height').
Then list visible things that match NO named part, with where they are.
Say 'cannot see' rather than guess."""

MERGE_PROMPT = """Two readers worked on a LEGEND-200 detector string. The text reader listed parts from the paper; the \
picture reader looked at several pictures, each on its own, with that list. Merge them:
1. For each part: the arrangement the pictures agree on (order, what rests on what, count, angles, ratio sizes), \
with which pictures support it; where the pictures disagree, say so and do not choose.
2. Questions for the picture reader for the next round: things the pictures can settle (e.g. 'is there a thin \
cylinder around the whole string?'). Say which picture to ask.
3. Questions for the text reader: visible things without a name, and sizes needed to turn ratios into mm.

TEXT READER:
{parts}

PICTURE READER:
{pictures}"""


def main(seed):
    out = ROOT / f"runs/ceiling/string_together/s{seed}"
    out.mkdir(parents=True, exist_ok=True)
    lines = TEXT.read_text().splitlines()
    passage = "\n".join(lines[109:160])          # the paper's description of strings, detectors and front end
    parts = call_llm("lbl/gpt-oss-120b", [{"role": "user", "content": TEXT_PROMPT.format(passage=passage)}],
                     stage="text_parts", seed=seed)["text"]
    (out / "text_parts.txt").write_text(parts)
    print("== text parts\n" + parts, flush=True)
    seen = {}
    for name, what in PICTURES.items():
        image = ROOT / "evidence/legend_detector_unit" / f"{name}.png"
        seen[name] = call_llm("lbl/gemma-4", [image_message(PICTURE_PROMPT.format(what=what, parts=parts), image)],
                              stage=f"picture_{name}", seed=seed)["text"]
        (out / f"{name}.txt").write_text(seen[name])
        print(f"== {name}\n{seen[name]}\n", flush=True)
    pictures = "\n\n".join(f"--- {n} ({PICTURES[n]})\n{t}" for n, t in seen.items())
    merged = call_llm("lbl/gpt-oss-120b", [{"role": "user", "content": MERGE_PROMPT.format(parts=parts, pictures=pictures)}],
                      stage="merge", seed=seed)["text"]
    (out / "merged.txt").write_text(merged)
    print("== merged\n" + merged, flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
