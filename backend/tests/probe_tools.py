import os
import json
import httpx

key = os.environ.get("OPENAI_API_KEY", "")
base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
model = os.environ.get("LLM_MODEL_TACTICAL", "gpt-5.6-luna")
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

tool = {
    "type": "function",
    "function": {
        "name": "select_tactical_option",
        "description": "Select one option",
        "parameters": {
            "type": "object",
            "properties": {
                "activation_id": {"type": "string"},
                "option_id": {"type": "string"},
                "fallback_policy": {"type": "string"},
            },
            "required": ["activation_id", "option_id", "fallback_policy"],
        },
    },
}

bodies = [
    {
        "model": model,
        "messages": [
            {"role": "system", "content": "Call the tool."},
            {"role": "user", "content": json.dumps({"activation_id": "a1", "options": [{"option_id": "o1"}]})},
        ],
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": "select_tactical_option"}},
        "temperature": 0.2,
    },
    {
        "model": model,
        "messages": [
            {"role": "system", "content": "Call the tool."},
            {"role": "user", "content": json.dumps({"activation_id": "a1", "options": [{"option_id": "o1"}]})},
        ],
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": "select_tactical_option"}},
        "max_completion_tokens": 200,
    },
]
for i, body in enumerate(bodies):
    r = httpx.post(base + "/chat/completions", headers=headers, json=body, timeout=45)
    print(f"CASE {i} -> {r.status_code}")
    print(r.text[:1200])
    print("---")
