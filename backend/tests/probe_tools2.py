import os
import json
import httpx

key = os.environ.get("OPENAI_API_KEY", "")
base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
model = os.environ.get("LLM_MODEL_TACTICAL", "gpt-5.6-luna")
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

tool_chat = {
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

# Chat with reasoning_effort none
body1 = {
    "model": model,
    "messages": [
        {"role": "system", "content": "Call the tool with option_id o1."},
        {"role": "user", "content": json.dumps({"activation_id": "a1", "options": [{"option_id": "o1"}, {"option_id": "o2"}]})},
    ],
    "tools": [tool_chat],
    "tool_choice": {"type": "function", "function": {"name": "select_tactical_option"}},
    "reasoning_effort": "none",
    "max_completion_tokens": 200,
}
r = httpx.post(base + "/chat/completions", headers=headers, json=body1, timeout=45)
print("CHAT none ->", r.status_code)
print(r.text[:1500])
print("---")

# Responses API tools
tool_resp = {
    "type": "function",
    "name": "select_tactical_option",
    "description": "Select one option",
    "parameters": tool_chat["function"]["parameters"],
}
body2 = {
    "model": model,
    "input": [
        {"role": "system", "content": "Call the tool with option_id o1."},
        {"role": "user", "content": json.dumps({"activation_id": "a1", "options": [{"option_id": "o1"}, {"option_id": "o2"}]})},
    ],
    "tools": [tool_resp],
    "tool_choice": {"type": "function", "name": "select_tactical_option"},
    "max_output_tokens": 200,
}
r = httpx.post(base + "/responses", headers=headers, json=body2, timeout=45)
print("RESPONSES ->", r.status_code)
print(r.text[:2000])
