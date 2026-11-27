#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trend-based content picker: asks OpenRouter LLM to pick the NEXT trending topic
for the channel (current cosmic/universe/mind-exploration buzz) and prints
JSON {"topic": "...", "moral": "..."}.
Used by the self-dev workflow so every episode is trend-driven instead of CSV-order.
"""
import os, sys, json, time, urllib.request

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
NICHET = os.environ.get("NICHET", "Cosmic universe / mind / brain exploration").strip()

def call_llm(sys_prompt, user_prompt):
    payload = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user_prompt}],
        "temperature": 0.8,
        "max_tokens": 1500,
        "reasoning": {"enabled": False},
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/NO-NAME7861/ahinikhlaq",
            "X-Title": "Universe Explorer Automation",
        })
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    content = resp["choices"][0]["message"]["content"].strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("no JSON in trend reply: " + content[:800])
    return json.loads(content[start:end + 1])

def pick():
    sys_prompt = (
        f"You are a trend researcher and scriptwriter for the '{NICHET}' niche. "
        "Look at the CURRENT trending topics, viral space news, cosmic discoveries, viral psychology "
        "moments and fan discussions in this niche RIGHT NOW (2026). Pick ONE fresh, trending story angle."
    )
    user_prompt = (
        "Suggest ONE trending episode topic for the next video (in English). "
        "Return ONLY valid JSON with keys: topic (short catchy phrase, max 80 chars), moral (one sentence lesson). "
        "No markdown fences, no extra text."
    )
    ep = call_llm(sys_prompt, user_prompt)
    topic = (ep.get("topic") or "").strip()
    moral = (ep.get("moral") or "").strip()
    if not topic:
        raise RuntimeError("trend picker returned empty topic: " + json.dumps(ep)[:500])
    return topic, moral

if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set - cannot pick trend")
    for attempt in range(3):
        try:
            topic, moral = pick()
            print(json.dumps({"topic": topic, "moral": moral}))
            break
        except SystemExit:
            raise
        except Exception as e:
            print(f"trend pick failed (attempt {attempt + 1}): {e}", file=sys.stderr, flush=True)
            if attempt < 2:
                time.sleep(10)
    sys.exit(0)
