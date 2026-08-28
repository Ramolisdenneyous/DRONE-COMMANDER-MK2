import os
import httpx

key = os.environ.get("OPENAI_API_KEY", "")
base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
model = os.environ.get("LLM_MODEL_TACTICAL", "gpt-5.6-luna")
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

cases = [
    ("chat", {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16}),
    ("chat", {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_completion_tokens": 16}),
    ("chat", {"model": model, "messages": [{"role": "user", "content": "ping"}]}),
    ("responses", {"model": model, "input": "ping", "max_output_tokens": 16}),
]
for kind, body in cases:
    url = base + ("/responses" if kind == "responses" else "/chat/completions")
    r = httpx.post(url, headers=headers, json=body, timeout=45)
    print(f"{kind} keys={list(body)} -> {r.status_code}")
    print(r.text[:800])
    print("---")
