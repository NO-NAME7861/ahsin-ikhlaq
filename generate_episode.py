#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ahsin Akhlaq — Universe & Philosophy Automation
Pipeline: LLM script (expert-level cosmology + philosophy, Hindi + English terms)
          -> NASA image library (real photos; Pollinations fallback, local starfield last resort)
          -> edge-tts en-IN Neerja expressive voice -> 1920x1080 video (Ken Burns + subtitles) -> YouTube upload -> Drive backup
Run locally (test):  DRY_RUN=1 python generate_episode.py
Run in CI:           private run first, then set UPLOAD=1
"""
import os, sys, json, csv, time, random, base64, asyncio, subprocess
import re
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

import quality  # script scoring + "beat the last episode" history

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
STATE_FILE = ROOT / "state" / "episodes.json"
EPISODES_CSV = ROOT / os.environ.get("EPISODES_CSV", "episodes.csv")
TOKEN_PATH = ROOT / "token.json"
PLAYLIST_ID = os.environ.get("PLAYLIST_ID", "").strip()  # optional override: uses this playlist for ALL episodes
PLAYLIST_TITLE = os.environ.get("PLAYLIST_TITLE", "Universe & Philosophy Deep Dives").strip()
WORK.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
CF_ACCOUNT_ID      = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN       = os.environ.get("CF_API_TOKEN", "").strip()
FALLBACK_MODELS    = [m for m in [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
] ]
VOICE              = os.environ.get("TTS_VOICE", "en-IN-NeerjaExpressiveNeural")   # Indian expressive female voice (English/Hinglish/Roman Urdu)
NARRATION_LANG     = os.environ.get("NARRATION_LANG", "hi").strip().lower()
ENGLISH_MODE       = NARRATION_LANG.startswith("en")
# +22% is the measured setting that makes this voice speak at ~200 words/minute in English.
TTS_RATE           = os.environ.get("TTS_RATE", "+22%" if ENGLISH_MODE else "+0%")
PRIVACY_STATUS     = os.environ.get("PRIVACY_STATUS", "private")  # safe default; set public when confident
UPLOAD             = os.environ.get("UPLOAD", "1") == "1"
DRY_RUN            = os.environ.get("DRY_RUN", "0") == "1"
EPISODE_OVERRIDE   = os.environ.get("EPISODE_INDEX", "").strip()  # force a specific episode id

TARGET_MINUTES     = int(os.environ.get("TARGET_MINUTES", "12"))   # minutes; <=14 keeps videos under the 15-minute upload limit for unverified channels. Raise via vars after phone verification (youtube.com/verify).
# Speech-rate targets for en-IN-NeerjaExpressiveNeural:
#   English at rate=+22%  -> ~200 words/min (user's chosen pace)
#   Romanized Hindi-Urdu  -> ~100 words/min at rate=+0%
# Use those rates so the final video matches TARGET_MINUTES even with LLM overshoot.
WORDS_PER_MIN      = 200 if ENGLISH_MODE else 100
WORDS_TARGET       = int(os.environ.get("WORDS_TARGET", str(TARGET_MINUTES * WORDS_PER_MIN)))
LONG_MODE          = TARGET_MINUTES >= 15
MAX_MINUTES        = float(os.environ.get("MAX_MINUTES", "14.2"))  # raise after channel verification
EPISODE_TOPIC      = os.environ.get("EPISODE_TOPIC", "").strip()   # one-off topic override (no csv edit)
EPISODE_MORAL      = os.environ.get("EPISODE_MORAL", "").strip()
W, H, FPS = 1920, 1080, 25
VIDEO_PRESET       = os.environ.get("VIDEO_PRESET", "fast")
VIDEO_CRF          = os.environ.get("VIDEO_CRF", "20")
_n_img_env = os.environ.get("N_IMAGES", "").strip()
N_IMAGES           = int(_n_img_env) if _n_img_env else (20 if LONG_MODE else 16)
CHANNEL_NAME = "Ahsin Akhlaq"

# Narration language switch: default is the channel's Romanized Hindi-Urdu,
# "en" produces a fully English episode (same voice, same pipeline).
LANG_STYLE = (
    "clear, vivid, neutral ENGLISH (simple words a 12-year-old understands, short sentences, "
    "no Hindi or Urdu phrases)"
    if ENGLISH_MODE else
    "natural, warm ROMANIZED Hindi-Urdu (Latin script, written exactly the way people text in "
    "India/Pakistan, e.g. 'Namaste doston, aaj sochenge...') with English technical terms "
    "embedded naturally (e.g., 'black hole', 'entropy', 'dark matter')"
)
SCRIPT_RULE = ("English only, Latin script." if ENGLISH_MODE
               else "NEVER Devanagari or Urdu script - Latin letters only")

# ---------------------------------------------------------------- helpers

def log(*a):
    print(f"[{datetime.now():%H:%M:%S}]", *a, flush=True)


def _seconds_until_upload_reset():
    """Seconds until YouTube's daily upload counter resets (midnight Pacific)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = timezone(timedelta(hours=-8))  # PST fallback
    now = datetime.now(tz)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60.0, (nxt - now).total_seconds())

AI_PHRASES = [
    r"AI[-]?generated", r"AI generated", r"AI[-]?narration", r"AI narration",
    r"AI[-]?content", r"AI content", r"artificial intelligence", r"synthetic content", r"\bAI\b",
]

def scrub_ai_text(text):
    if not text:
        return text
    out = text
    for pattern in AI_PHRASES:
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip(" -â€”:,.;")
    return out or text

def load_episode():
    if EPISODE_TOPIC:
        return {
            "id": EPISODE_OVERRIDE or "special",
            "topic": EPISODE_TOPIC,
            "moral": EPISODE_MORAL or "Wonder is the beginning of wisdom",
        }
    rows = list(csv.DictReader(open(EPISODES_CSV, encoding="utf-8")))
    assert rows, "episodes.csv empty"
    if EPISODE_OVERRIDE:
        row = next((r for r in rows if r["id"] == EPISODE_OVERRIDE), None)
        if not row:
            sys.exit(f"EPISODE_INDEX {EPISODE_OVERRIDE} not found in episodes.csv")
        return row
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"next_id": rows[0]["id"], "done": []}
    row = next((r for r in rows if r["id"] == state.get("next_id")), rows[0])
    return row

def mark_done(ep_id):
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"next_id": None, "done": []}
    done = state.get("done", [])
    if ep_id not in done:
        done.append(ep_id)
    rows = list(csv.DictReader(open(EPISODES_CSV, encoding="utf-8")))
    ids = [r["id"] for r in rows]
    nxt = ids[(ids.index(ep_id) + 1) % len(ids)]  # cycle
    STATE_FILE.write_text(json.dumps({"next_id": nxt, "done": done}, indent=2, ensure_ascii=False))
    log(f"state -> next episode id = {nxt}")

# ---------------------------------------------------------------- 1. script

def _call_llm_once(model, row, sys_prompt, user_prompt, max_tokens=7500, expect_json=True):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user_prompt}],
        "temperature": 0.8,
        "max_tokens": max_tokens,
        "reasoning": {"enabled": False},
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/NO-NAME7861/universe-explorer",
            "X-Title": "Universe Explorer Automation",
        })
    with urllib.request.urlopen(req, timeout=240) as r:
        resp = json.loads(r.read())

    content = None
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("unexpected LLM payload: " + json.dumps(resp)[:1500])
    if not content:
        raise RuntimeError("empty content: " + json.dumps(resp)[:1500])

    content = content.strip()
    if not expect_json:
        return content
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("no JSON in reply: " + content[:1500])
    return json.loads(content[start:end + 1])

def _has_non_latin_script(text):
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F or 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
            return True
    return False

def _ensure_latin_script(row, sys_prompt, ep):
    """Neerja voices cannot speak Devanagari/Urdu script - force Latin-script output."""
    narr = (ep.get("narration") or "").strip()
    if not _has_non_latin_script(narr):
        return ep
    log("narration contains non-Latin script - retrying with a strict romanization instruction")
    romanize_prompt = f"""Your narration for the episode below contained characters in Devanagari or Urdu script. REWRITE the ENTIRE narration in ROMAN/Latin script transliterated Hindi-Urdu (e.g., 'Dosto, aaj hum sochenge...') - EVERY word must be Latin letters, ZERO Devanagari or Urdu characters. Keep the same content, same 6-10 scene structure, same warm second-person 'aap' voice, same word target of about {WORDS_TARGET} words. Reply ONLY with the narration as plain text - no JSON, no markdown, no commentary.

Episode topic: {row['topic']}
Central insight: {row['moral']}

Previous narration (for reference, do NOT reuse its script):
{narr}"""
    try:
        fixed = _llm_with_fallback(sys_prompt, romanize_prompt, 8000, "romanize", expect_json=False)
        fixed = (fixed or "").strip()
        if fixed and not _has_non_latin_script(fixed):
            ep["narration"] = fixed
            log("narration rewritten in Latin script")
        else:
            log("WARNING: romanize retry still contains non-Latin chars - TTS may fail")
    except SystemExit as e:
        log(f"romanize retry failed: {e}")
    return ep

def _ensure_narration_length(row, sys_prompt, ep):
    """If the narration came out too short, ask the LLM for one expanded rewrite."""
    narr = (ep.get("narration") or "").strip()
    wc = len(narr.split())
    floor = int(WORDS_TARGET * 0.75)
    if wc >= floor:
        return ep
    log(f"narration too short ({wc} words < {floor}) - requesting an expanded version")
    expand_prompt = f"""Below is a narration draft ({wc} words) for this episode. REWRITE and EXPAND it to a MINIMUM of {WORDS_TARGET} words in {LANG_STYLE}. {SCRIPT_RULE} Keep every fact accurate (no claims beyond the draft's scope), keep the 6-10 scene paragraph structure, keep the warm direct-address voice. Reply ONLY with the expanded narration as plain text - no JSON, no markdown, no commentary.

Episode topic: {row['topic']}
Central insight: {row['moral']}

DRAFT NARRATION:
{narr}"""
    try:
        expanded = _llm_with_fallback(sys_prompt, expand_prompt, 8000, "expand", expect_json=False)
        w2 = len(expanded.split())
        log(f"expanded narration: {w2} words (was {wc})")
        if w2 > wc and not _has_non_latin_script(expanded):
            ep["narration"] = expanded.strip()
        elif w2 > wc:
            log("expanded narration contains non-Latin script - keeping original")
    except SystemExit as e:
        log(f"expand failed, keeping original {wc}-word narration: {e}")
    return ep

def call_llm(row):
    sys_prompt = (
        f"You are a world-class science communicator and philosopher writing for the YouTube channel '{CHANNEL_NAME}', "
        "a deep-dive channel that merges cutting-edge universe exploration, human psychology and profound philosophy. "
        "You combine the rigor of a textbook, the storytelling of Carl Sagan, and the depth of a philosophy "
        f"seminar. You write in {LANG_STYLE}. You NEVER fabricate facts: use real missions (Voyager, JWST, LIGO, "
        "Event Horizon Telescope, New Horizons), real scientists and psychologists (Einstein, Sagan, Hawking, Noether, "
        "Festinger, Loftus, Kahneman), real theories, real numbers and dates. If a fact is uncertain or debated, say so honestly. "
        "Use SIMPLE language that a 12-year-old can understand. Short sentences. "
        "Natural spoken rhythm: direct address, rhetorical questions, breath-catching pauses. "
        "EDITING PLAYBOOK (modeled on popular science channels): "
        "1) First line = HOOK question, max 20 words, curiosity gap. "
        "2) Average sentence under 15 words; no sentence over 30 words. "
        "3) New scene every ~50 seconds; visual change expected. "
        "4) Ask a small question every 2-3 sentences to keep brain engaged. "
        "5) Facts cited inline (name + year + source), never vague 'experts say'. "
        "6) End with one philosophical line, then silence, then sources line. "
        "7) Title = curiosity gap, max 65 chars, no punctuation except ':' and '?'. "
        "8) NEVER use phrases like 'AI-generated', 'AI narration', 'artificial intelligence'."

        "Never use phrases like 'AI-generated', 'AI content', 'AI narration', or 'artificial intelligence' in the title or description. "
        "Reply ONLY with valid JSON, no markdown fences."
    )
    n_img_prompts = N_IMAGES
    user_prompt = f"""Write one complete deep-dive episode in this exact JSON shape:
{{
 "title": "YouTube title, max 70 chars, expert curiosity-gap ENGLISH ONLY, e.g. 'What Happens Inside a Black Hole? The Information Paradox Explained'",
 "description": "2-3 sentence hook + 1 line central insight + line: 'Sources: NASA, ESA, peer-reviewed journals.' + subscribe CTA, max 1000 chars. ENGLISH ONLY. Do NOT mention AI, artificial intelligence, AI-generated visuals, AI narration, or synthetic content.",
 "tags": ["max 15 tags, ENGLISH ONLY"],
 "moral": "one sentence â€” the episode's central philosophical insight",
 "narration": "EXACTLY {WORDS_TARGET} words (plus-minus 5%) - hard cap {WORDS_TARGET + 150} words; never exceed the cap. continuous narration in {LANG_STYLE}. {SCRIPT_RULE} Simple words, short sentences, direct address: you-voice, rhetorical questions, breath-catching pauses. Split into 6-10 scenes (separated by paragraph breaks) so viewers never feel a dull moment. Each scene: a precise scientific fact/mechanism -> its deeper meaning -> a philosophical question it raises. Include REAL numbers, names, dates. MUST end with the central philosophical insight. Speak like a brilliant, warm storyteller who reads research papers for a living.",
 "image_prompts": ["{n_img_prompts} SHORT prompts, each: photorealistic, cinematic, dramatic lighting, ultra detailed, no text, no watermark, <scene description: e.g. 'interior of an accretion disk around a supermassive black hole seen from a nearby camera, gravitational lensing, photon ring'>. Use space imagery: nebulae, exoplanets, observatories, astronauts, planet surfaces, deep field images, star clusters."],
  "image_queries": ["{n_img_prompts} SHORT NASA-image-library search phrases matching the prompts above, each 2-4 words, e.g. 'black hole accretion disk', 'james webb deep field', 'voyager spacecraft', 'orion nebula hubble'. Pure ASCII, no punctuation."],
 "thumbnail_prompt": "one dramatic photorealistic prompt for a 16:9 thumbnail, high contrast, no text, no watermark",
  "thumbnail_query": "2-4 word NASA search phrase for the thumbnail, e.g. 'earth from space'",
  "thumbnail_hook": "2-4 word ALL-CAPS curiosity hook for the thumbnail, e.g. 'WHERE IS EVERYONE?' or 'YOUR BRAIN LIES' - English only, no ending period"
}}

Episode brief (topic + central insight):
Topic seed: {row['topic']}
Central insight: {row['moral']}

{quality.prompt_context()}"""

    if LONG_MODE:
        ep = call_llm_long(row, sys_prompt, user_prompt)
        log("LLM OK via long-form mode (3 narrations stitched)")
        return ep

    ep = _llm_with_fallback(sys_prompt, user_prompt, 8000, "episode")
    ep = _ensure_latin_script(row, sys_prompt, ep)
    return _ensure_narration_length(row, sys_prompt, ep)

# ---- long-form (50-minute) mode -------------------------------------------

def _llm_with_fallback(sys_prompt, user_prompt, max_tokens, label, expect_json=True):
    models = [OPENROUTER_MODEL] + [m for m in FALLBACK_MODELS if m != OPENROUTER_MODEL]
    failures = []
    for model in models:
        for attempt in range(3):
            try:
                ep = _call_llm_once(model, None, sys_prompt, user_prompt, max_tokens, expect_json)
                log(f"LLM OK via {model} ({label}, attempt {attempt + 1})")
                return ep
            except Exception as e:
                log(f"model {model} {label} attempt {attempt + 1} failed: {e}")
                failures.append(f"{model}: {e}")
                time.sleep(20)
    sys.exit(f"All LLM models failed ({label}):\n" + "\n\n".join(failures))

def call_llm_long(row, sys_prompt, _unused):
    """50-minute episodes: meta + 3 narration parts stitched (free models cap output)."""
    meta_prompt = f"""Write ONLY the metadata for one long-form ({TARGET_MINUTES}-minute) deep-dive episode. Reply with valid JSON:
{{
 "title": "YouTube title, max 70 chars, expert curiosity-gap ENGLISH ONLY",
 "description": "2-3 sentence hook + 1 line central insight + line: 'Sources: NASA, ESA, peer-reviewed journals.' + subscribe CTA, max 1000 chars. ENGLISH ONLY. Do NOT mention AI, artificial intelligence, AI-generated visuals, AI narration, or synthetic content.",
 "tags": ["max 15 tags, ENGLISH ONLY"],
 "moral": "one sentence â€” the episode's central philosophical insight",
 "image_prompts": ["{N_IMAGES} SHORT prompts, each: photorealistic, cinematic, dramatic lighting, ultra detailed, no text, no watermark, <scene description>. Space imagery throughout."],
  "image_queries": ["{N_IMAGES} SHORT NASA-image-library search phrases matching the prompts above, each 2-4 words, e.g. 'black hole accretion disk', 'james webb deep field', 'voyager spacecraft', 'orion nebula hubble'. Pure ASCII, no punctuation."],
 "thumbnail_prompt": "one dramatic photorealistic prompt for a 16:9 thumbnail, high contrast, no text, no watermark",
  "thumbnail_query": "2-4 word NASA search phrase for the thumbnail, e.g. 'earth from space'",
  "thumbnail_hook": "2-4 word ALL-CAPS curiosity hook for the thumbnail, e.g. 'WHERE IS EVERYONE?' or 'YOUR BRAIN LIES' - English only, no ending period",
 "outline": ["8 scene summaries with the key scientific facts, numbers and philosophers to cover, in order â€” this is the plan for the 3 narrative parts"]
}}

Topic seed: {row['topic']}
Central insight: {row['moral']}

{quality.prompt_context()}"""
    meta = _llm_with_fallback(sys_prompt, meta_prompt, 4500, "meta")
    outline = meta.get("outline", [])
    outline_txt = "\n".join(f"Scene {i+1}: {o}" for i, o in enumerate(outline))

    parts = []
    for part_no in (1, 2, 3):
        part_prompt = f"""You are writing PART {part_no} of 3 narration parts for ONE long-form ({TARGET_MINUTES}-minute) deep-dive episode
(target total {WORDS_TARGET} words; this part MUST be ~{WORDS_TARGET // 3} words (plus/minus 10%), written in {LANG_STYLE}, {SCRIPT_RULE} Natural spoken rhythm, paragraph breaks every few sentences.

Episode topic: {row['topic']}
Central insight: {row['moral']}

{quality.prompt_context()}

FULL OUTLINE (do NOT repeat what other parts cover - write ONLY your assigned scenes):
{outline_txt}

PART {part_no} ASSIGNMENT:
{'Open the episode with a powerful hook. Cover outline scenes 1-3. End part 1 on a cliffhanger.' if part_no == 1 else ('Continue from part 1. Cover outline scenes 4-6. Keep tension rising. End part 2 mid-crescendo.' if part_no == 2 else 'Now land the plane. Cover the remaining outline scenes. End with the central philosophical insight, delivered with awe.')}

Reply with plain text ONLY (no JSON, no markdown) - just the narration, ready for voiceover."""
        part = _llm_with_fallback(sys_prompt, part_prompt, 6000, f"narration-part-{part_no}", expect_json=False)
        parts.append(part.strip())

    ep = dict(meta)
    ep.pop("outline", None)
    ep["narration"] = "\n\n".join(p.strip() for p in parts)
    wc = len(ep["narration"].split())
    log(f"long-form narration assembled: {wc} words")
    if wc < WORDS_TARGET * 0.6:
        log("WARNING: narration shorter than expected â€” video may be shorter than target")
    return ep

# ---------------------------------------------------------------- 2. images

def _cf_image(prompt, dest, seed):
    import base64
    payload = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        data=payload, method="POST",
        headers={"Authorization": f"Bearer {CF_API_TOKEN}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    img_b64 = resp.get("result", {}).get("image")
    if not img_b64:
        raise RuntimeError("CF AI failed: " + json.dumps(resp)[:500])
    dest.write_bytes(base64.b64decode(img_b64))
    return True

def _http_get(url, timeout=90, min_bytes=15_000):
    req = urllib.request.Request(url, headers={"User-Agent": "UniverseExplorerBot/1.0 (https://github.com/NO-NAME7861/universe-explorer)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < min_bytes:
        raise RuntimeError(f"too small ({len(data)} bytes): {url[:120]}")
    # sanity: JPEG (FF D8) or PNG (89 50)
    if data[:2] not in (b"\xff\xd8", b"\x89P"):
        raise RuntimeError(f"not an image ({data[:32]!r}): {url[:120]}")
    return data

def _nasa_image(query, dest):
    """Fetch a real space photo from the NASA image library (free, no key, public domain)."""
    if not query:
        return False
    search = ("https://images-api.nasa.gov/search?q=" + urllib.parse.quote(query)
              + "&media_type=image&page_size=12")
    req = urllib.request.Request(search, headers={"User-Agent": "UniverseExplorerBot/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    items = data.get("collection", {}).get("items", [])
    for size_pref in ("~large.jpg", "~medium.jpg", "~small.jpg"):
        for item in items:
            for link in item.get("links", []):
                href = (link.get("href") or "").strip()
                if href.lower().endswith(size_pref):
                    try:
                        img = _http_get(href, timeout=120, min_bytes=20_000)
                        dest.write_bytes(img)
                        return True
                    except Exception:
                        continue
    # last NASA chance: any .jpg href we can find
    for item in items:
        for link in item.get("links", []):
            href = (link.get("href") or "").strip()
            if href.lower().endswith(".jpg"):
                try:
                    img = _http_get(href, timeout=120, min_bytes=20_000)
                    dest.write_bytes(img)
                    return True
                except Exception:
                    continue
    return False

def _starfield_image(dest, seed):
    """Bulletproof local fallback: deep-space gradient + stars rendered with PIL."""
    import random
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    top, bottom = (10, 16, 48), (2, 4, 14)   # deep indigo -> near black
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        px_row = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
        for x in range(W):
            px[x, y] = px_row
    # soft nebula glows
    overlay = Image.new("RGB", (W, H), (0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for _ in range(4):
        cx, cy = rnd.randint(0, W), rnd.randint(0, H)
        rx, ry = rnd.randint(W // 5, W // 2), rnd.randint(H // 5, H // 2)
        hue = rnd.choice([(80, 40, 160), (30, 90, 170), (150, 60, 120), (20, 120, 150)])
        od.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=hue)
    overlay = overlay.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, Image.blend(img, overlay, 0.55), 0.6)
    d = ImageDraw.Draw(img)
    # stars
    for _ in range(420):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        b = rnd.choice([110, 150, 190, 230, 255])
        d.point((x, y), fill=(b, b, b))
    for _ in range(40):
        x, y = rnd.randint(2, W - 3), rnd.randint(2, H - 3)
        r = rnd.choice([1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    # a few hero stars with cross glare
    for _ in range(5):
        x, y = rnd.randint(40, W - 40), rnd.randint(40, H - 40)
        d.line([(x - 14, y), (x + 14, y)], fill=(230, 230, 255), width=1)
        d.line([(x, y - 14), (x, y + 14)], fill=(230, 230, 255), width=1)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 255))
    img.save(dest, "PNG")
    return True

def gen_image(prompt, dest, seed, query=None):
    """1) NASA image library (real photos)  2) Pollinations  3) local starfield (always works)."""
    try:
        if _nasa_image(query or prompt, dest):
            log("image from NASA library:", (query or prompt)[:60])
            return True
    except Exception as e:
        log("NASA image lookup failed, trying generators:", e)
    for attempt in range(2):
        try:
            url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
                   + f"?width={W}&height={H}&nologo=true&seed={seed}")
            data = _http_get(url, timeout=150, min_bytes=15_000)
            dest.write_bytes(data)
            log("image from Pollinations")
            return True
        except Exception as e:
            log(f"pollinations attempt {attempt + 1}/2 failed: {e}")
            time.sleep(8)
    try:
        _starfield_image(dest, seed)
        log("image = local starfield fallback (all online sources failed)")
        return True
    except Exception as e:
        log("WARNING: even starfield fallback failed:", e)
        return False

# ---------------------------------------------------------------- 3. voice

def run_tts(text_file, mp3, srt):
    voices = [VOICE] + [v for v in ("en-IN-NeerjaNeural", "en-IN-PrabhatNeural") if v != VOICE]
    last_err = None
    for voice in voices:
        for attempt in range(2):
            try:
                cmd = [sys.executable, "-m", "edge_tts", "--file", str(text_file),
                       "--write-media", str(mp3), "--write-subtitles", str(srt),
                       "--voice", voice, f"--rate={TTS_RATE}"]
                subprocess.run(cmd, check=True)
                log(f"TTS OK with voice {voice}")
                return
            except subprocess.CalledProcessError as e:
                last_err = e
                log(f"TTS attempt {attempt + 1}/2 with {voice} failed ({e}) - retrying")
                time.sleep(5)
    sys.exit(f"edge-tts failed for every voice ({voices}); last error: {last_err}")

def media_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]).decode().strip()
    return float(out)

# ---------------------------------------------------------------- 4. video

KZ_IN  = "z='min(zoom+0.0011,1.18)'"          # zoom in
KZ_OUT = "z='if(eq(on,1),1.18,max(1.001,zoom-0.0016))'"  # zoom out

def make_segment(img, seg, d, zoom_in):
    frames = max(int(d * FPS), FPS)
    z = KZ_IN if zoom_in else KZ_OUT
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"zoompan={z}:d={frames}:s={W}x{H}:fps={FPS},"
          f"eq=brightness=0.0,format=yuv420p")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", f"{d:.3f}",
           "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", VIDEO_PRESET,
           "-crf", VIDEO_CRF, str(seg)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mix_narration_with_bgm(audio):
    """Mix narration with looping epic ambient BGM at low volume."""
    bgm = ROOT / "assets" / "music" / "epic_ambient.mp3"
    if not bgm.exists():
        log("BGM missing - skipping mix")
        return audio
    dur = media_duration(audio)
    mixed = WORK / "narration_mix.mp3"
    fade_end = max(0.1, dur - 6)
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(bgm), "-i", str(audio),
        "-filter_complex",
        f"[1:a]volume=1.0[n];[0:a]volume=0.08,"
        f"afade=t=in:st=0:d=6,afade=t=out:st={fade_end:.2f}:d=6[m];"
        f"[n][m]amix=inputs=2:duration=first:dropout_transition=2,"
        f"loudnorm[a]",
        "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "3", str(mixed)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("BGM mixed with narration (volume 0.16 + loudnorm)")
    return mixed

def build_video(image_paths, audio, srt, out_mp4, thumb):
    audio = mix_narration_with_bgm(audio)
    total = media_duration(audio)
    per = total / len(image_paths)
    segs = []
    for i, img in enumerate(image_paths):
        seg = WORK / f"seg_{i:02d}.mp4"
        make_segment(img, seg, per, zoom_in=(i % 2 == 0))
        segs.append(seg)
        log(f"segment {i + 1}/{len(image_paths)} done ({per:.1f}s)")

    list_file = WORK / "concat.txt"
    list_file.write_text("\n".join(f"file '{s.as_posix()}'" for s in segs))
    concat = WORK / "concat.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                    "-c", "copy", str(concat)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    font_size = max(20, int(30 * H / 1080))
    margin_v = max(24, int(40 * H / 1080))
    sub_style = (f"FontName=Noto Sans,FontSize={font_size},Bold=-1,PrimaryColour=&H00FFFFFF,"
                 f"OutlineColour=&H00000000,BorderStyle=4,Outline=2,Shadow=0,MarginV={margin_v}")
    subprocess.run(["ffmpeg", "-y", "-i", str(concat), "-i", str(audio),
                    "-vf", f"subtitles={srt.as_posix()}:force_style='{sub_style}'",
                    "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", VIDEO_CRF,
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_mp4)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("video ready:", out_mp4)

# ---------------------------------------------------------------- 5. upload

def youtube_upload(ep, mp4, thumbnail):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    if not TOKEN_PATH.exists():
        sys.exit("token.json missing - run get_token.py first (while signed into the NEW Google account)")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": ep["title"][:100],
            "description": ep["description"],
            "tags": ep.get("tags", [])[:15],
            "categoryId": "27",  # Education
            "defaultLanguage": "en" if ENGLISH_MODE else "hi",
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(mp4), chunksize=16 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    log("uploading to YouTube ...")

    def _do_upload():
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        r = None
        while r is None:
            status, r = req.next_chunk()
            if status:
                log(f"upload {int(status.progress() * 100)}%")
        return r

    resp = None
    for attempt in range(2):
        try:
            resp = _do_upload()
            break
        except Exception as e:
            if "uploadLimitExceeded" in str(e) and attempt == 0:
                wait = _seconds_until_upload_reset()
                log(f"YouTube daily upload cap reached; sleeping {wait / 60:.0f} min "
                    "until the midnight-Pacific reset, then retrying once")
                time.sleep(wait)
                continue
            raise
    vid = resp["id"]
    log(f"uploaded: https://youtu.be/{vid}")

    if thumbnail and Path(thumbnail).exists():
        thumb_path = Path(thumbnail)
        size_kb = thumb_path.stat().st_size // 1024
        for attempt in range(3):
            try:
                yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb_path))).execute()
                log(f"thumbnail set ({size_kb} KB)")
                break
            except Exception as e:
                msg = str(e)
                log(f"thumbnail attempt {attempt + 1}/3 failed: {msg[:300]}")
                if attempt < 2:
                    time.sleep(20 + attempt * 20)
        else:
            log("WARNING: thumbnail could not be set - video has an auto frame thumbnail")
    return vid

def drive_backup(mp4):
    # Optional: needs token_drive.json (separate token, Drive scope only -
    # Google forbids mixing YouTube and Drive scopes in one consent)
    drive_token = ROOT / "token_drive.json"
    if not drive_token.exists():
        log("drive backup skipped - token_drive.json not present (optional)")
        return
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = Credentials.from_authorized_user_file(str(drive_token), SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    q = "name='UniverseExplorer' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    folders = drive.files().list(q=q, fields="files(id)").execute().get("files", [])
    if folders:
        fid = folders[0]["id"]
    else:
        fid = drive.files().create(body={"name": "UniverseExplorer",
                                          "mimeType": "application/vnd.google-apps.folder"},
                                    fields="id").execute()["id"]
    drive.files().create(body={"name": Path(mp4).name, "parents": [fid]},
                         media_body=MediaFileUpload(str(mp4)),
                         fields="id").execute()
    log("backed up to Google Drive /UniverseExplorer")

# ---------------------------------------------------------------- playlist

def playlist_for(title=None, desc=None, lang="hi"):
    """Return a playlist ID by title, creating it if missing."""
    if PLAYLIST_ID and not title:
        return PLAYLIST_ID
    title = title or PLAYLIST_TITLE
    desc = desc or ("Universe exploration and philosophy deep dives. "
                    "Every episode explores one profound question about the cosmos and the human condition.")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == title:
                return item["id"]
        p = yt.playlists().insert(part="snippet,status",
            body={"snippet": {"title": title, "description": desc, "defaultLanguage": lang},
                  "status": {"privacyStatus": "public"}}).execute()
        log(f"created playlist: {title} -> {p['id']}")
        return p["id"]
    except Exception as e:
        log("WARNING: playlist lookup failed:", e)
        return None

# Pillar playlists - every new episode is added to its pillar as well as the
# main deep-dives playlist, so the channel reads as three clear series.
PILLAR_PLAYLISTS = {
    "cosmos": ("Cosmos Files",
               "Deep dives into black holes, galaxies, quantum physics and the origin of the universe."),
    "mind": ("The Mind Files",
             "Consciousness, perception and the self - where neuroscience meets philosophy."),
    "brain": ("Brain Traps",
              "Psychology, biases and the hidden machinery of everyday decisions."),
}

def add_to_playlist(video_id, pillar=None):
    targets = []
    main = playlist_for()
    if main:
        targets.append(main)
    if pillar in PILLAR_PLAYLISTS:
        t, d = PILLAR_PLAYLISTS[pillar]
        pid = playlist_for(t, d, "en")
        if pid and pid not in targets:
            targets.append(pid)
    if not targets:
        log("no playlist id - skipping playlist add")
        return
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    for pid in targets:
        try:
            yt.playlistItems().insert(part="snippet",
                body={"snippet": {"playlistId": pid,
                                  "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            log(f"added to playlist {pid}")
        except Exception as e:
            log(f"playlist add failed ({pid}, non-fatal):", e)

# ---------------------------------------------------------------- main

IMAGE_SUFFIX = (", photorealistic, cinematic, dramatic lighting, ultra detailed, "
                "documentary style, no text, no watermark")
THUMB_SUFFIX = (", photorealistic, cinematic, dramatic, high contrast, no text, no watermark")


def _hook_from_title(title: str) -> str:
    """Fallback thumbnail hook when the LLM did not return one."""
    t = (title or "").split(":")[0].split("?")[0].strip()
    words = [w for w in t.replace("-", " ").split() if w.lower() not in
             ("the", "a", "an", "of", "and", "why", "how", "what", "is", "are")]
    return " ".join(words[:3]).upper() or "THE UNIVERSE"


def revise_episode(row, ep, result):
    """One targeted rewrite pass that fixes exactly what the scorer flagged.

    Only the words change - the visual plan (image prompts/queries) is kept, so
    this costs one LLM call and no extra images.
    """
    issues = "\n".join(f"- {i}" for i in result.get("issues", [])) or "- tighten everything"
    current = {k: ep.get(k) for k in
               ("title", "description", "tags", "moral", "narration", "thumbnail_hook")}
    prompt = f"""A quality checker scored this episode {result['score']}/100. Rewrite it so it scores higher.

Fix EVERY problem below, without losing scientific accuracy or inventing facts:
{issues}

Hard rules:
- narration must stay about {WORDS_TARGET} words (plus/minus 5%), 6-10 scenes separated by blank lines
- {LANG_STYLE}; {SCRIPT_RULE}
- keep the same topic and the same central insight
- title max 70 characters, English only
- thumbnail_hook is 2-4 words, ALL CAPS
- never mention AI, artificial intelligence, AI-generated or synthetic content

Current episode JSON:
{json.dumps(current, ensure_ascii=False)}

Reply with the SAME JSON shape (title, description, tags, moral, narration, thumbnail_hook) and nothing else."""
    try:
        fixed = _llm_with_fallback(
            "You are a ruthless YouTube script editor. You fix weak hooks, vague claims, "
            "padded writing and long sentences. You never invent facts. "
            "Reply ONLY with valid JSON, no markdown fences.",
            prompt, 8000, "quality-revision")
    except Exception as e:
        log("quality revision failed (non-fatal):", e)
        return None
    if not isinstance(fixed, dict) or not (fixed.get("narration") or "").strip():
        log("quality revision returned no narration - keeping original")
        return None
    for key in ("title", "description", "tags", "moral", "narration", "thumbnail_hook"):
        if fixed.get(key):
            ep[key] = fixed[key]
    ep["title"] = scrub_ai_text(ep.get("title", ""))
    ep["description"] = scrub_ai_text(ep.get("description", ""))
    return ep


def main():
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set")

    row = load_episode()
    log(f"episode: {row['id']} | {row['topic']}")

    ep = call_llm(row)
    ep["title"] = scrub_ai_text(ep.get("title", ""))
    ep["description"] = scrub_ai_text(ep.get("description", ""))
    log("LLM wrote:", ep["title"])

    # --- quality gate -------------------------------------------------------
    # Score the script, do ONE targeted rewrite if it is below the target
    # (every episode must beat the best previous one), then record the result
    # so state/quality.json feeds lessons into tomorrow's prompt.
    result = quality.score_episode(ep, row, WORDS_TARGET)
    target = quality.target_score()
    log(f"quality score {result['score']}/100 (target {target}+)")
    if result["issues"]:
        log("issues:", "; ".join(result["issues"]))
    if row["id"] == "special":
        # One-off specials (thank-you, announcements) must not be rewritten into
        # deep dives and must not sit on the normal quality ladder.
        log("one-off special: revision skipped, not added to the quality ladder")
    else:
        if result["score"] < target and os.environ.get("QUALITY_REVISE", "1") == "1":
            revised = revise_episode(row, ep, result)
            if revised:
                r2 = quality.score_episode(revised, row, WORDS_TARGET)
                log(f"revision score {r2['score']}/100")
                if r2["score"] >= result["score"]:
                    ep, result = revised, r2
        quality.record(row["id"], result, {"title": ep.get("title", "")[:90]})
        log(f"final quality {result['score']}/100 "
            f"(best so far {quality.load_history().get('best', 0)})")

    (WORK / "episode.json").write_text(json.dumps(ep, indent=2, ensure_ascii=False))

    narration = ep["narration"]
    (WORK / "narration.txt").write_text(narration, encoding="utf-8")
    log(f"narration words: {len(narration.split())}")

    prompts = ep["image_prompts"][:N_IMAGES]
    queries = ep.get("image_queries") or []
    image_paths = []
    seed0 = random.randint(1000, 999999)
    for i, p in enumerate(prompts):
        dest = WORK / f"img_{i:02d}.png"
        q = queries[i] if i < len(queries) else None
        if gen_image(p + IMAGE_SUFFIX, dest, seed0 + i, query=q):
            image_paths.append(dest)
        time.sleep(2)
    if len(image_paths) < 8:
        sys.exit(f"only {len(image_paths)} images generated - aborting")

    mp3, srt = WORK / "narration.mp3", WORK / "narration.srt"
    run_tts(WORK / "narration.txt", mp3, srt)
    dur = media_duration(mp3)
    log(f"narration audio duration: {dur:.1f}s ({dur / 60:.1f} min)")
    if dur > MAX_MINUTES * 60:
        sys.exit(f"narration too long for the current limit ({dur / 60:.1f} min > {MAX_MINUTES:.1f} min). "
                 "Raise MAX_MINUTES after verifying the channel (youtube.com/verify), or lower TARGET_MINUTES/WORDS_TARGET.")

    thumb_base = WORK / "thumb_base.png"
    thumb_q = ep.get("thumbnail_query") or (queries[0] if queries else "galaxy cosmos")
    gen_image(ep.get("thumbnail_prompt", prompts[0]) + THUMB_SUFFIX, thumb_base, seed0 + 999, query=thumb_q)

    # Branded 1280x720 thumbnail: bold hook text + pillar badge (COSMOS/MIND/BRAIN).
    from thumbnail import make_thumbnail, pillar_for
    hook = (ep.get("thumbnail_hook") or "").strip() or _hook_from_title(ep.get("title", ""))
    pillar = (row.get("pillar") or "").strip().lower()
    if pillar not in ("cosmos", "mind", "brain"):
        pillar = pillar_for(row["topic"] + " " + ep.get("title", ""))
    thumb = WORK / "thumb.jpg"
    make_thumbnail(thumb_base, hook, pillar, thumb)
    log(f"thumbnail built (hook='{hook}', pillar={pillar})")

    out_mp4 = WORK / f"episode_{row['id']}.mp4"
    build_video(image_paths, mp3, srt, out_mp4, thumb)

    if DRY_RUN or not UPLOAD:
        log("DRY_RUN/UPLOAD=0 - skipping upload. Video at:", out_mp4)
        return

    vid = youtube_upload(ep, out_mp4, thumb)
    add_to_playlist(vid, pillar)
    try:
        drive_backup(out_mp4)
    except Exception as e:
        log("drive backup failed (non-fatal):", e)
    if row["id"] in {r["id"] for r in csv.DictReader(open(EPISODES_CSV, encoding="utf-8"))}:
        mark_done(row["id"])
    else:
        log("one-off episode (not in episodes.csv) - rotation state left untouched")
    log("done -> https://youtu.be/" + vid)

if __name__ == "__main__":
    main()
