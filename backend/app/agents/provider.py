"""LLM provider adapters for tactical option selection and radio."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("uvicorn.error")

SELECT_TOOL = {
    "type": "function",
    "function": {
        "name": "select_tactical_option",
        "description": "Select exactly one offered tactical option.",
        "parameters": {
            "type": "object",
            "properties": {
                "activation_id": {"type": "string"},
                "option_id": {"type": "string"},
                "fallback_policy": {
                    "type": "string",
                    "enum": ["next_best_target", "nearest_cover", "continue_objective", "return_to_signal", "hold"],
                },
                "reason": {"type": "string"},
            },
            "required": ["activation_id", "option_id", "fallback_policy"],
        },
    },
}


class ProviderError(Exception):
    pass


def select_tactical_option(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    activation_id: str,
    offered_option_ids: list[str],
) -> dict[str, Any]:
    """Call OpenAI gpt-5.6-luna to pick an option_id via tool call."""
    if not settings.llm_external_enabled or not settings.openai_api_key:
        raise ProviderError("LLM disabled or missing API key")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
    ]
    body = {
        "model": settings.llm_model_tactical,
        "messages": messages,
        "tools": [SELECT_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "select_tactical_option"}},
        # Luna requires reasoning_effort=none for function tools on chat.completions
        "reasoning_effort": "none",
        "max_completion_tokens": 300,
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=settings.llm_decision_timeout_sec) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                raise ProviderError(f"{resp.status_code}: {resp.text[:400]}")
            data = resp.json()
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(str(exc)) from exc

    try:
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            raise ProviderError("No tool call in response")
        args = json.loads(tool_calls[0]["function"]["arguments"])
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"Malformed tool response: {exc}") from exc

    option_id = args.get("option_id")
    if option_id not in offered_option_ids:
        raise ProviderError(f"Unoffered option_id {option_id}")
    if args.get("activation_id") != activation_id:
        raise ProviderError("activation_id mismatch")
    return {
        "option_id": option_id,
        "fallback_policy": args.get("fallback_policy", "hold"),
        "reason": args.get("reason", ""),
        "raw": {"model": settings.llm_model_tactical, "usage": data.get("usage")},
    }


def generate_radio_line(*, facts: dict[str, Any], unit_name: str) -> str:
    if not settings.llm_external_enabled or not settings.openai_api_key:
        return _fallback_radio(facts, unit_name)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly squad/drone radio voice. "
                "Reply with ONE short factual acknowledgement sentence based only on the provided facts. "
                "No coordinates invention. No dice talk."
            ),
        },
        {"role": "user", "content": json.dumps({"unit": unit_name, "facts": facts})},
    ]
    body = {
        "model": settings.llm_model_radio,
        "messages": messages,
        "reasoning_effort": "none",
        "max_completion_tokens": 60,
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=settings.llm_radio_timeout_sec) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if not text:
                return _fallback_radio(facts, unit_name)
            return text.split("\n")[0][:180]
    except Exception:
        return _fallback_radio(facts, unit_name)


def _fallback_radio(facts: dict[str, Any], unit_name: str) -> str:
    sub = facts.get("subroutine", "action")
    return f"{unit_name}: {sub} complete."
