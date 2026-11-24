#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quality gate for Ahsin Akhlaq episodes.

Every generated script is scored 0-100 on things that actually move retention
and trust: hook strength, fact density, sentence length, structure, length
accuracy, repetition, vague claims and packaging.

The pipeline keeps state/quality.json:
  - per-episode scores (so each video must beat the last one)
  - recurring issues turned into "lessons" that are injected into the next
    prompt, closing the improvement loop.
"""
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QFILE = ROOT / "state" / "quality.json"
LEARN = ROOT / "state" / "learning.json"

BANNED = [
    r"\bAI\b", r"AI[- ]?generated", r"artificial intelligence", r"synthetic content",
]
VAGUE = [
    r"experts say", r"scientists say", r"studies show", r"research shows",
    r"it is said", r"many believe", r"some people think",
]
# names that signal a real, checkable fact rather than hand-waving
FACT_NAMES = (
    "nasa", "esa", "jaxa", "cern", "ligo", "jwst", "hubble", "voyager", "cassini",
    "new horizons", "apollo", "artemis", "perseverance", "curiosity", "kepler",
    "einstein", "hawking", "sagan", "newton", "bohr", "planck", "schrodinger",
    "schrödinger", "heisenberg", "noether", "fermi", "drake", "kardashev",
    "penrose", "hawking", "chalmers", "dennett", "koch", "tononi", "libet",
    "metzinger", "seth", "kahneman", "tversky", "festinger", "loftus", "milgram",
    "asch", "zimbardo", "seligman", "dunning", "kruger", "cacioppo", "keltner",
    "gazzaniga", "sperry", "ramachandran", "damasio", "edelman", "crick",
    "m87", "sagittarius a*", "andromeda", "betelgeuse", "proxima", "kepler-",
    "ligo", "virgo", "event horizon telescope", "planck", "wmap", "cobe",
)
UNITS = (
    "km", "km/s", "light-year", "light year", "parsec", "billion", "million",
    "trillion", "percent", "%", "degrees", "kelvin", "celsius", "years", "seconds",
    "minutes", "hertz", "electron volt", "ev", "solar mass", "au",
)


def _sents(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _words(text):
    return re.findall(r"[A-Za-z0-9'’\-]+", text or "")


def _paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def score_episode(ep, row=None, words_target=1200):
    """Return {'score': int, 'breakdown': {...}, 'issues': [...]}."""
    narr = (ep.get("narration") or "").strip()
    title = (ep.get("title") or "").strip()
    hook_txt = (ep.get("thumbnail_hook") or "").strip()
    words = _words(narr)
    wc = len(words)
    sents = _sents(narr)
    paras = _paragraphs(narr)
    low = narr.lower()
    issues = []
    b = {}

    # 1) hook -----------------------------------------------------------------
    opening = " ".join(sents[:2])
    ow = len(_words(opening))
    hook = 0
    if opening.endswith("?") or "?" in opening:
        hook += 7
    if re.search(r"\d", opening):
        hook += 5
    if re.search(r"\b(you|your|aap|tum)\b", opening, re.I):
        hook += 3
    if ow <= 30:
        hook += 5
    else:
        issues.append(f"Opening hook is {ow} words - tighten it under 30.")
    b["hook"] = min(20, hook)

    # 2) fact density ---------------------------------------------------------
    years = len(re.findall(r"\b(1[6-9]\d{2}|20\d{2})\b", narr))
    numbers = len(re.findall(r"\b\d[\d,.]*\b", narr))
    names = sum(low.count(n) for n in FACT_NAMES)
    units = sum(low.count(u) for u in UNITS)
    fact_points = min(20, years * 2 + min(8, names) + min(6, units) + min(6, numbers // 3))
    b["facts"] = fact_points
    if fact_points < 12:
        issues.append("Too few checkable facts - add real years, numbers, mission/person names.")
    if years == 0:
        issues.append("No dates at all - anchor the story in real years.")

    # 3) structure ------------------------------------------------------------
    avg_len = sum(len(_words(s)) for s in sents) / max(1, len(sents))
    long_sents = sum(1 for s in sents if len(_words(s)) > 30)
    struct = 0
    # Long-form episodes are stitched from 3 parts, so they naturally have more scenes.
    lo, hi = (15, 45) if (words_target or 0) > 4000 else (6, 12)
    if lo <= len(paras) <= hi:
        struct += 6
    else:
        issues.append(f"{len(paras)} scenes - aim for {lo}-{hi} paragraphs.")
    if avg_len <= 15:
        struct += 5
    else:
        issues.append(f"Average sentence is {avg_len:.0f} words - cut to under 15.")
    if long_sents <= max(1, len(sents) // 20):
        struct += 4
    else:
        issues.append(f"{long_sents} sentences are over 30 words - split them.")
    b["structure"] = min(15, struct)

    # 4) length accuracy ------------------------------------------------------
    if words_target:
        err = abs(wc - words_target) / words_target
        if err <= 0.05:
            length = 12
        elif err <= 0.10:
            length = 9
        elif err <= 0.18:
            length = 5
        else:
            length = 0
            issues.append(f"Length is {wc} words vs target {words_target} - off by {err*100:.0f}%.")
    else:
        length = 10
    b["length"] = length

    # 5) repetition -----------------------------------------------------------
    grams = Counter(tuple(words[i:i + 5]) for i in range(max(0, len(words) - 4)))
    repeated = [g for g, c in grams.items() if c >= 3]
    rep = 6 if not repeated else max(0, 6 - len(repeated))
    b["repetition"] = rep
    if repeated:
        issues.append("Repeated phrases detected - vary the wording.")

    # 6) vague claims / banned ------------------------------------------------
    vague_hits = sum(len(re.findall(p, low)) for p in VAGUE)
    banned_hits = sum(len(re.findall(p, low, re.I)) for p in BANNED)
    clar = 10 - vague_hits * 2 - banned_hits * 5
    b["clarity"] = max(0, min(10, clar))
    if vague_hits:
        issues.append("Replace vague 'experts say' claims with named sources.")
    if banned_hits:
        issues.append("Remove any AI/artificial-intelligence wording.")

    # 7) ending ---------------------------------------------------------------
    ending = " ".join(sents[-2:])
    end_pts = 0
    if "?" in ending:
        end_pts += 3
    if re.search(r"\b(meaning|perhaps|maybe|choose|remember|we are|hum)\b", ending, re.I):
        end_pts += 3
    b["ending"] = min(5, end_pts)

    # 8) packaging ------------------------------------------------------------
    pack = 0
    if title and len(title) <= 70:
        pack += 4
    else:
        issues.append("Title over 70 characters - shorten it.")
    if re.search(r"[:?]", title):
        pack += 2
    hw = len(hook_txt.split())
    if 2 <= hw <= 4:
        pack += 4
    else:
        issues.append("Thumbnail hook must be 2-4 words.")
    b["packaging"] = min(10, pack)

    score = int(sum(b.values()))
    return {"score": score, "breakdown": b, "issues": issues,
            "words": wc, "scenes": len(paras), "avg_sentence": round(avg_len, 1)}


def load_history():
    if QFILE.exists():
        try:
            return json.loads(QFILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"history": [], "best": 0, "lessons": []}


def save_history(h):
    QFILE.parent.mkdir(parents=True, exist_ok=True)
    QFILE.write_text(json.dumps(h, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def last_score():
    h = load_history()
    return h["history"][-1]["score"] if h.get("history") else 0


def target_score():
    """Each episode should beat the best one so far (floor 80)."""
    h = load_history()
    return max(80, int(h.get("best", 0)) + 1)


def record(ep_id, result, extra=None):
    h = load_history()
    h.setdefault("history", []).append({
        "id": ep_id,
        "score": result["score"],
        "breakdown": result["breakdown"],
        "issues": result["issues"],
        "words": result.get("words"),
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **(extra or {}),
    })
    h["best"] = max(int(h.get("best", 0)), result["score"])
    h["lessons"] = _derive_lessons(h)
    save_history(h)
    return h


def _derive_lessons(h):
    """Turn recurring issues into short prompt instructions."""
    recent = h.get("history", [])[-10:]
    counter = Counter()
    for item in recent:
        for issue in item.get("issues", []):
            key = issue.split(" - ")[0].strip()
            counter[key] += 1
    lessons = []
    mapping = {
        "Opening hook is": "Open with one concrete number or a direct question under 18 words.",
        "Too few checkable facts": "Include at least 12 checkable facts: years, numbers, mission names, researchers.",
        "No dates at all": "Name real years for every major claim.",
        "Average sentence is": "Keep the average sentence under 15 words.",
        "sentences are over 30 words": "Never write a sentence longer than 30 words.",
        "Length is": "Hit the word target within 5%.",
        "Repeated phrases detected": "Do not reuse the same phrase or metaphor.",
        "Replace vague": "Never write 'experts say' - name the person and year.",
        "Remove any AI": "Never mention AI or artificial intelligence.",
        "Title over 70": "Keep titles under 70 characters.",
        "Thumbnail hook must be": "Return a 2-4 word thumbnail hook in ALL CAPS.",
        "scenes - aim for": "Use 6-10 paragraph breaks (scenes).",
    }
    for key, count in counter.most_common(6):
        if count >= 2:
            for prefix, lesson in mapping.items():
                if key.startswith(prefix):
                    lessons.append(lesson)
                    break
    # keep the best-performing lessons from analytics if present
    try:
        if LEARN.exists():
            lj = json.loads(LEARN.read_text(encoding="utf-8"))
            for lesson in lj.get("lessons", []):
                if lesson not in lessons:
                    lessons.append(lesson)
    except Exception:
        pass
    return lessons[:8]


def prompt_context(max_lessons=6):
    """Text block injected into the next generation prompt."""
    h = load_history()
    prev = h["history"][-1] if h.get("history") else None
    lines = []
    if prev:
        lines.append(
            f"Previous episode scored {prev['score']}/100. This episode MUST score higher "
            f"(target {max(80, prev['score'] + 1)}+). Weaknesses last time: "
            + ("; ".join(prev.get("issues", [])) or "none")
            + "."
        )
    lessons = h.get("lessons", [])[:max_lessons]
    if lessons:
        lines.append("Standing quality rules learned from past episodes:")
        lines += [f"- {l}" for l in lessons]
    return "\n".join(lines)


if __name__ == "__main__":
    print(json.dumps(load_history(), indent=2)[:2000])
