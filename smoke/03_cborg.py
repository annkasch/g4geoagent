"""Smoke test 3: call CBorg with text and with an image, and see which models can read it.

Each model gets the cross-section from test 1 and must name the parts, their
materials and the z range of the crystal (37 to 69 mm).

    python smoke/03_cborg.py           needs CBORG_API_KEY and smoke/out/crystal.png
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from g4geoagent.agent.llm import call_llm, image_message

OUT = Path(__file__).parent / "out"

# Only the free LBL-hosted models. The paid models that the first run of this test (2026-10-08) also tried are
# kept below for the record; call_llm refuses them unless G4GEO_ALLOW_PAID=1 is set.
MODELS = ["lbl/cborg-vision", "lbl/cborg-chat", "lbl/gemma-4", "lbl/gpt-oss-120b"]
PAID_MODELS_NOT_RUN = [
    "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5",
    "gpt-5.5", "gpt-5.4-mini",
    "gemini-3.1-pro", "gemini-3.5-flash",
    "xai/grok-4.3", "google/qwen-3",
]

QUESTION = ("This is a cross-section of a detector. List every labelled part with "
            "its material. Then give the z range of the green part in mm, read from "
            "the axis. Answer in at most four lines.")
PARTS = ["endcap", "G4_Al", "vacuum", "G4_Galactic", "crystal", "G4_Ge"]


def ask(model):
    try:
        answer = call_llm(model, [image_message(QUESTION, OUT / "crystal.png")])
    except Exception as error:   # a model without vision input fails here
        return {"asked": model, "error": f"{type(error).__name__}: {str(error)[:200]}"}
    text = answer["text"]
    answer["asked"] = model
    answer["reads_labels"] = all(p.lower() in text.lower() for p in PARTS)
    answer["reads_axis"] = "37" in text and "69" in text
    return answer


if __name__ == "__main__":
    text = call_llm(MODELS[1], [{"role": "user", "content": "Reply with the single word: ready"}])
    print(f"text call: {text['model']} said {text['text']!r}, cost ${text['cost_usd']}")
    assert "ready" in text["text"].lower()
    assert text["cost_usd"] is not None, "no x-litellm-response-cost header"

    with ThreadPoolExecutor(len(MODELS)) as pool:
        results = list(pool.map(ask, MODELS))
    (OUT / "cborg_vision.json").write_text(json.dumps(results, indent=1))

    print(f"\n{'asked':20s} {'answered by':34s} labels axis  cost")
    for r in results:
        if "error" in r:
            print(f"{r['asked']:20s} FAILED  {r['error'][:90]}")
        else:
            cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] is not None else "?"
            print(f"{r['asked']:20s} {r['model']:34s} {'yes' if r['reads_labels'] else 'NO':6s} "
                  f"{'yes' if r['reads_axis'] else 'NO':5s} {cost}")

    assert any(r.get("reads_labels") for r in results), "no model could read the image"
    print("\nPASS  answers in", OUT / "cborg_vision.json")
