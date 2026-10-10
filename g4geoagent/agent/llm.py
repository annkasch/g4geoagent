"""All LLM calls go through call_llm(), which talks to CBorg (LBL's LiteLLM proxy)."""

import base64
import json
import os
import time
from functools import cache
from pathlib import Path

import openai
from pydantic import ValidationError

CBORG_URL = "https://api.cborg.lbl.gov"
DEFAULT_OPTIONS = {}      # sent with every call, e.g. {"seed": 1} to get a fresh answer instead of a cached one


@cache
def _client():
    return openai.OpenAI(api_key=os.environ["CBORG_API_KEY"], base_url=CBORG_URL,
                         max_retries=3, timeout=300)


def image_message(text, image_path):
    """A user message with text and one PNG image."""
    data = base64.b64encode(Path(image_path).read_bytes()).decode()
    return {"role": "user", "content": [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
    ]}


def call_llm(model, messages, log=None, stage="", **options):
    """Send `messages` to `model`. Returns the answer with the model and cost.

    Keys: text, model, cost_usd, input_tokens, output_tokens, seconds.
    With `log` (a RunLog) the call is recorded under `stage`.
    """
    options = {**DEFAULT_OPTIONS, **options}
    start = time.time()
    raw = _client().chat.completions.with_raw_response.create(
        model=model, messages=messages, **options)
    response = raw.parse()
    cost = raw.headers.get("x-litellm-response-cost")
    answer = {
        "text": response.choices[0].message.content or "",
        "model": response.model,
        "cost_usd": float(cost) if cost else None,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "seconds": round(time.time() - start, 2),
    }
    if log:
        log.event("llm_call", stage, **{k: v for k, v in answer.items() if k != "text"})
    return answer


def _json_part(text):
    """The JSON object in an answer, without code fences or words around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[start:end + 1], strict=False)   # line breaks inside strings are accepted


def call_llm_json(model, messages, schema, log=None, stage="", attempts=3, **options):
    """Like call_llm, but the answer must be JSON that fits the pydantic `schema`.

    An answer that does not fit is sent back with the error, up to `attempts` times.
    Returns (validated object, answer dict of the last call).
    """
    messages = list(messages)
    for attempt in range(attempts):
        answer = call_llm(model, messages, log=log, stage=stage, **options)
        try:
            return schema.model_validate(_json_part(answer["text"])), answer
        except (ValueError, ValidationError) as error:
            if log:
                log.event("invalid_answer", stage, model=model, attempt=attempt, error=str(error)[:500])
            messages += [{"role": "assistant", "content": answer["text"]},
                         {"role": "user", "content": f"That was not valid. Error:\n{str(error)[:1500]}\n"
                                                     "Answer again with only the corrected JSON object."}]
    raise ValueError(f"{model} gave no valid {schema.__name__} in {attempts} attempts")
