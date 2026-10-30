"""Token Factory client. Every LLM call goes through call_json(): parse, validate, retry once, else None."""
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

from shipcheck import config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

MAX_CALLS = 3  # hard bound on API calls per call_json()


class LLMError(Exception):
    """Token Factory unreachable or refusing (auth, credits, rate limit). Callers should fall back to cached examples."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


_client: Optional[OpenAI] = None
_stats_lock = threading.Lock()


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.NEBIUS_API_KEY:
            raise LLMError("NEBIUS_API_KEY is not set")
        _client = OpenAI(base_url=config.TOKEN_FACTORY_BASE_URL, api_key=config.NEBIUS_API_KEY,
                         timeout=config.LLM_TIMEOUT_S, max_retries=2)
    return _client


_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _clean(text: str) -> str:
    """Strip reasoning blocks, code fences and surrounding prose, leaving the JSON object."""
    text = _THINK.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i != -1 and j > i else text.strip()


def _record(stats: Optional[Dict[str, Any]], model: str, usage: Any, seconds: float, reasoning: bool) -> None:
    if stats is None:
        return
    with _stats_lock:
        s = stats.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                     "seconds": 0.0, "reasoning_seen": False})
        s["calls"] += 1
        s["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        s["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        s["seconds"] += seconds
        s["reasoning_seen"] = s["reasoning_seen"] or reasoning


def _complete(model: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float,
              thinking: Optional[bool], stats: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    kwargs: Dict[str, Any] = {}
    if thinking is not None:
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": thinking}}
    t = time.time()
    try:
        r = get_client().chat.completions.create(model=model, messages=messages, max_tokens=max_tokens,
                                                 temperature=temperature, **kwargs)
    except APIStatusError as e:
        raise LLMError(f"Token Factory HTTP {e.status_code}: {e.message}", e.status_code) from e
    except APIConnectionError as e:
        raise LLMError(f"Token Factory unreachable: {e}") from e
    choice = r.choices[0]
    msg = choice.message
    reasoning = bool(getattr(msg, "reasoning_content", None) or (msg.model_extra or {}).get("reasoning_content"))
    _record(stats, model, r.usage, time.time() - t, reasoning)
    return msg.content or "", choice.finish_reason


def call_json(model: str, prompt: str, schema: Type[T], max_tokens: int, *, system: Optional[str] = None,
              temperature: float = 0.2, thinking: Optional[bool] = None,
              stats: Optional[Dict[str, Any]] = None) -> Optional[T]:
    """Ask `model` for a JSON object matching `schema`.

    Returns the validated object, or None if the model never produced valid output (callers treat that as
    "unclear"). Raises LLMError when the API itself fails. Makes at most MAX_CALLS API calls.
    """
    max_tokens = min(max_tokens, config.MAX_TOKENS_CEILING)
    user = (f"{prompt}\n\nReturn ONLY a JSON object (no prose, no code fences) matching this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    fixed_once = False

    for _ in range(MAX_CALLS):
        content, finish = _complete(model, messages, max_tokens, temperature, thinking, stats)
        truncated = finish == "length"
        if truncated:  # reasoning or a long answer ate the budget: allow more next time
            max_tokens = min(max_tokens * 2, config.MAX_TOKENS_CEILING)
        if not content.strip():
            log.warning("%s returned empty content (finish=%s)", model, finish)
            if truncated:
                continue
            return None
        try:
            return schema.model_validate_json(_clean(content))
        except ValidationError as e:
            if fixed_once and not truncated:
                log.warning("%s output failed validation twice: %s", model, str(e)[:300])
                return None
            fixed_once = True
            log.warning("%s output invalid, retrying: %s", model, str(e)[:300])
            messages = messages + [
                {"role": "assistant", "content": content[:4000]},
                {"role": "user", "content": f"That output was invalid: {str(e)[:800]}\n"
                                            "Return ONLY the corrected JSON object."},
            ]
    return None


if __name__ == "__main__":
    # Smoke test: python -m shipcheck.llm  (a few calls, well under $0.01)
    from typing import Literal

    class Probe(BaseModel):
        status: Literal["pass", "fail"]
        reason: str

    q = 'Requirement: "Repo has an open-source license detected by GitHub." Fact: GitHub reports spdx_id = MIT.'
    runs = [("Nano", config.MODEL_NANO, config.MAX_TOKENS_NANO, None),
            ("Nano, thinking off", config.MODEL_NANO, config.MAX_TOKENS_NANO, False),
            ("Super", config.MODEL_SUPER, config.MAX_TOKENS_SUPER, None)]
    for label, model, budget, thinking in runs:
        stats: Dict[str, Any] = {}
        try:
            out = call_json(model, q, Probe, budget, thinking=thinking, stats=stats)
            print(f"[{'PASS' if out else 'FAIL'}] {label}: {out!r}\n       {stats.get(model)}")
        except LLMError as e:
            print(f"[FAIL] {label}: LLMError {e}")
