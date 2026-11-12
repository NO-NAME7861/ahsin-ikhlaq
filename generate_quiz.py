#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universe & Philosophy — manual quiz generator (for Studio → Community tab).
Creates 2 quiz prompts per day; saves to quizzes/quiz-<date>.md and commits+pushes.
You paste the two questions manually into Studio Community → Poll/Post.
"""
import os, sys, json, re, time, subprocess, random
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
QUIZ_DIR = ROOT / "quizzes"
QUIZ_DIR.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
FALLBACK_MODELS    = [m for m in [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
]]

def call_llm(prompt, max_tokens=1800):
    models = [OPENROUTER_MODEL] + [m for m in FALLBACK_MODELS if m != OPENROUTER_MODEL]
    for model in models:
        for attempt in range(2):
            try:
                payload = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9,
                    "max_tokens": max_tokens,
                    "reasoning": {"enabled": False},
                }).encode()
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=payload, method="POST",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                             "Content-Type": "application/json",
                             "HTTP-Referer": "https://github.com/NO-NAME7861/universe-explorer",
                             "X-Title": "Ahsin Akhlaq Quiz"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp = json.loads(r.read())
                content = resp["choices"][0]["message"]["content"].strip()
                if content:
                    print(f"LLM OK via {model}")
                    return content
                raise RuntimeError("empty")
            except Exception as e:
                print(f"{model} attempt {attempt + 1} failed: {e}")
                time.sleep(8)
    sys.exit("all models failed")

def commit_file(filename):
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=str(ROOT), check=False)
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=str(ROOT), check=False)
    subprocess.run(["git", "add", str(filename)], cwd=str(ROOT), check=False)
    cr = subprocess.run(["git", "commit", "-m", f"chore: add quizzes {filename.name}"], cwd=str(ROOT),
                        capture_output=True)
    print("commit exit:", cr.returncode, cr.stdout.decode()[-300:], cr.stderr.decode()[-300:])
    pp = subprocess.run(["git", "push", "origin", "main"], cwd=str(ROOT),
                        capture_output=True)
    print("push exit:", pp.returncode)
    err = (pp.stderr or b"").decode()
    if pp.returncode != 0:
        print("push error:", err[-400:])

def main():
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set")

    # PKT date with Urdu label for file name (ASCII only)
    pkt_now = datetime.now(timezone(timedelta(hours=5)))
    tag = pkt_now.strftime("%Y-%m-%d")

    prompt = f"""You are writing TWO YouTube Community forum quizzes about cosmos and philosophy for a Pakistani-Urdu audience. The audience likes deep science explained simply with English technical terms.

Reply ONLY with valid JSON in this shape (no markdown, no extra text):
{{
  "quizzes": [
    {{
      "question": "ENGLISH question (multiple choice welcome, ending with a hint of wonder) — max 140 chars",
      "options": ["option A", "option B", "option C", "option D"],
      "answer_index": 1,
      "explanation": "one short line, English, why that is correct — max 80 chars"
    }},
    {{
      "question": "ENGLISH question — max 140 chars",
      "options": ["option A", "option B", "option C", "option D"],
      "answer_index": 2,
      "explanation": "one short line, English — max 80 chars"
    }}
  ]
}}

Rules:
- One question MUST be pure astronomy/cosmology, one MUST be philosophy/stoicism/big-picture.
- Options must be plausible and self-consistent; avoid obviously-wrong throwaway options.
- Keep it fun, not textbook-dry.
Topic date: {tag}."""

    raw = call_llm(prompt, max_tokens=1600)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        sys.exit("no JSON in reply")
    data = json.loads(m.group(0))
    quizzes = data.get("quizzes", [])
    assert len(quizzes) == 2, "expected 2 quizzes"

    md_lines = [
        f"# Quizzes — {tag}",
        "",
        "These two quizzes are for the **#ahsin-ikhlaq** channel → Studio → Community → Poll or Post.",
        "",
        "Just copy-paste each question with its options. Members win by commenting.",
        "",
    ]
    for i, q in enumerate(quizzes, 1):
        md_lines += [
            f"## Quiz {i}",
            f"",
            f"**{q['question']}**",
            f"",
            f"A) {q['options'][0]}",
            f"B) {q['options'][1]}",
            f"C) {q['options'][2]}",
            f"D) {q['options'][3]}",
            f"",
            f"Answer: {chr(64 + int(q['answer_index']) + 1)}",
            f"Explanation: {q['explanation']}",
            f"",
            f"---",
        ]

    filename = QUIZ_DIR / f"quiz-{tag}.md"
    filename.write_text("\n".join(md_lines), encoding="utf-8")
    print("wrote", filename)
    commit_file(filename)

if __name__ == "__main__":
    main()
