"""Step 1 of the string test: what the picture model reads about a LEGEND-200 string's arrangement from pictures alone.

    python experiments/ceiling/string_pictures.py <seed>

Each picture is read on its own (no paper text). Answers go to runs/ceiling/string_pictures/s<seed>/.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))

from g4geoagent.agent.llm import call_llm, image_message   # noqa: E402

PICTURES = {
    "string_photo": "a photo of one detector string being assembled in a glove box",
    "unit_render": "a rendering of one detector unit of the string",
    "unit_photo_pen_plate": "a close-up photo of the underside of one detector unit",
    "array_render": "a rendering of the whole detector array",
}

PROMPT = """This is {what} of the LEGEND-200 germanium detector array. Describe, only from what you can SEE, how the \
parts are arranged, as a person building a simulation model would need it:
- which parts there are (say how each looks: colour, shape, material if it is evident);
- their order from top to bottom, and which part rests on, hangs from or is clamped to which;
- how many of each repeated part, and how they are spread (around an axis, at what angles, in a row);
- which way parts face (up/down, towards the axis or away);
- gaps and proportions you can estimate, as ratios to a part you name (e.g. 'gap about 1/5 of the detector height');
- what you cannot see or are unsure about.
Do not use knowledge of the experiment beyond the picture; say 'cannot see' instead of guessing."""


def main(seed):
    out = ROOT / f"runs/ceiling/string_pictures/s{seed}"
    out.mkdir(parents=True, exist_ok=True)
    for name, what in PICTURES.items():
        image = ROOT / "evidence/legend_detector_unit" / f"{name}.png"
        answer = call_llm("lbl/gemma-4", [image_message(PROMPT.format(what=what), image)],
                          stage=f"picture_{name}", seed=seed)["text"]
        (out / f"{name}.txt").write_text(answer)
        print(f"== {name}\n{answer}\n", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
