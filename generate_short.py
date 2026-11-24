#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ahsin Akhlaq — Universe & Philosophy SHORTS Automation
Pipeline: LLM (45-55s vertical Short, Romanized Hindi-Urdu + English) -> NASA image library (Pollinations fallback, local starfield last resort)
          -> edge-tts en-IN Neerja expressive voice -> 1080x1920 Ken Burns video w/ big captions + BGM
          -> YouTube upload (auto-detected Short because 9:16 & <60s)
Run locally (test):  DRY_RUN=1 python generate_short.py
"""
import os, sys, json, csv, time, random, base64, asyncio, subprocess, re
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work_shorts"
STATE_FILE = ROOT / "state" / "shorts.json"
TOKEN_PATH = ROOT / "token.json"
PLAYLIST_TITLE = os.environ.get("SHORTS_PLAYLIST_TITLE", "Universe & Philosophy Shorts").strip()
WORK.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
FALLBACK_MODELS    = [m for m in [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
] ]
VOICE              = os.environ.get("TTS_VOICE", "en-IN-NeerjaExpressiveNeural")  # Indian expressive female (Hinglish/Roman Urdu)
NARRATION_LANG     = os.environ.get("NARRATION_LANG", "hi").strip().lower()
ENGLISH_MODE       = NARRATION_LANG.startswith("en")
PURE_URDU_MODE     = NARRATION_LANG == "ur"   # pure Roman Urdu, Latin script, simple words, no English technical terms
TTS_RATE           = os.environ.get("TTS_RATE", "+22%" if ENGLISH_MODE else "+0%")
PRIVACY_STATUS     = os.environ.get("PRIVACY_STATUS", "private")
UPLOAD             = os.environ.get("UPLOAD", "1") == "1"
DRY_RUN            = os.environ.get("DRY_RUN", "0") == "1"
SHORTS_INDEX       = os.environ.get("SHORTS_INDEX", "").strip()

# Narration style for Shorts: English mode, pure Roman Urdu mode, or default Romanized Hindi-Urdu.
SHORT_STYLE = (
    "clear, vivid, neutral ENGLISH (simple words a 12-year-old understands, short sentences, no Hindi or Urdu phrases)"
    if ENGLISH_MODE else
    "pure ROMAN URDU, Latin script only, simple words a 12-year-old understands, short sentences, "
    "natural spoken Urdu, warm second person address, NO English words or English technical terms"
    if PURE_URDU_MODE else
    "natural, warm ROMANIZED Hindi-Urdu (Latin script, transliterated) with English technical terms"
)

W, H, FPS = 1080, 1920, 30
N_IMAGES = 5

CHANNEL_NAME = "Ahsin Akhlaq"
TOPICS = [
    "Why the sky is dark at night", "What a light-year really means", "The Fermi paradox",
    "How old is the universe", "What the Big Bang theory actually says", "Dark matter explained",
    "Dark energy and cosmic acceleration", "Why stars twinkle", "Black holes explained",
    "Event horizon of a black hole", "Hawking radiation", "The heat death of the universe",
    "Neutron star mergers", "What is a supernova", "Pulsars", "Quasars", "The Andromeda galaxy",
    "The Milky Way's black hole", "How astronauts sleep in space", "The James Webb Space Telescope",
    "Pale Blue Dot", "What cosmic inflation means", "Cosmic microwave background", "Why we are stardust",
    "The Drake equation", "The Great Filter", "Are we alone in the universe", "Exoplanets",
    "The Goldilocks zone", "Ocean moons of Jupiter and Saturn", "Mars terraforming ethics",
    "Why Mars is red", "Venus: Earth's evil twin", "Titan's methane lakes", "Europa's ocean",
    "The Pale Blue Dot again", "Carl Sagan's legacy", "Why astronauts see the Overview Effect",
    "How rockets escape Earth", "The Kármán line", "Gravity assists explained", "Lagrange points",
    "The Apollo missions' legacy", "Voyager 1 among the stars", "Voyager 2 among the stars",
    "The Golden Record", "Are we living in a simulation", "The multiverse theory", "The fine-tuning problem",
    "The anthropic principle", "Einstein and time dilation", "Quantum entanglement",
    "Schrödinger's cat", "The uncertainty principle", "Wave-particle duality", "The arrow of time",
    "Entropy explained", "Second law of thermodynamics", "Boltzmann brains", "The measure problem",
    "Eternal inflation", "Bubble universes", "Calabi-Yau manifolds", "M-theory explained",
    "String theory", "Quantum gravity", "The holographic principle",
    "What is consciousness", "Philosophy of mind in space", "Stoicism and the cosmos",
    "Nietzsche and the abyss", "Buddhism and impermanence", "Existentialism and the stars",
    "Meaning in an infinite universe", "The overview effect psychology",
    "Overview effect's impact on behavior", "Why we fear the cosmic void", "The sublime and the universe",
    "Mysteries of the night sky", "Why do we exist at all", "The fine-tuning argument",
    "What lies beyond the observable universe", "The edge of the universe", "Cosmic dawn",
    "The first stars", "The reionization epoch", "Cosmic dawn light", "The universe's first light",
    # psychology (the channel's third pillar: universe + philosophy + mind)
    "Cognitive dissonance explained", "Why your brain rewrites your memories",
    "The bystander effect", "Why time feels faster as you age", "The Dunning-Kruger effect",
    "Learned helplessness", "The spotlight effect", "Why we procrastinate",
    "The science of habit loops", "The Zeigarnik effect", "Cognitive biases that fool you daily",
    "The mere exposure effect", "Why multitasking fails", "The peak-end rule",
    "Loss aversion explained", "The placebo effect", "Why you can't stop scrolling",
    "Attachment styles explained", "The misinformation effect", "Why memory is a reconstruction",
]

ANGLES = [
    "as a 30-second mind-blower", "as a practical lesson for daily life",
    "as a philosophical question", "as a historical mystery", "as a scientific breakthrough",
    "as a 'what if' scenario", "as a profound analogy", "as a warning from the cosmos",
    "as pure wonder", "as a reason to stay curious",
]

def log(*a):
    print(f"[{datetime.now():%H:%M:%S}]", *a, flush=True)

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
    out = re.sub(r"\s{2,}", " ", out).strip(" -—:,.;")
    return out or text

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"next_id": "001", "done": [], "count": 0}

def mark_done(ep_id):
    state = load_state()
    done = state.get("done", [])
    if ep_id not in done:
        done.append(ep_id)
    n = int(ep_id)
    STATE_FILE.write_text(json.dumps({"next_id": f"{n+1:03d}", "done": done, "count": len(done)},
                                     indent=2, ensure_ascii=False))

def _call_llm_once(model, sys_prompt, user_prompt, max_tokens=2500):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user_prompt}],
        "temperature": 0.85,
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
            "X-Title": "Ahsin Akhlaq Shorts",
        })
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.loads(r.read())
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("unexpected LLM payload: " + json.dumps(resp)[:1200])
    if not content:
        raise RuntimeError("empty content: " + json.dumps(resp)[:1200])
    return content.strip()

def call_llm(sys_prompt, user_prompt, max_tokens=2500):
    models = [OPENROUTER_MODEL] + [m for m in FALLBACK_MODELS if m != OPENROUTER_MODEL]
    failures = []
    for model in models:
        for attempt in range(2):
            try:
                out = _call_llm_once(model, sys_prompt, user_prompt, max_tokens)
                log(f"LLM OK via {model} attempt {attempt+1}")
                return out
            except Exception as e:
                log(f"model {model} attempt {attempt+1} failed: {e}")
                failures.append(f"{model}: {e}")
                time.sleep(10)
    sys.exit("All LLM models failed:\n" + "\n".join(failures))

def extract_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise RuntimeError("no JSON in reply: " + text[:1200])
    return json.loads(text[s:e+1])

def _http_get(url, timeout=90, min_bytes=15_000):
    req = urllib.request.Request(url, headers={"User-Agent": "UniverseExplorerBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < min_bytes:
        raise RuntimeError(f"too small ({len(data)} bytes)")
    if data[:2] not in (b"\xff\xd8", b"\x89P"):
        raise RuntimeError(f"not an image: {data[:32]!r}")
    return data

def _nasa_image(query, dest):
    """Real space photos from the NASA image library (free, no key, public domain)."""
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
                        dest.write_bytes(_http_get(href, timeout=120, min_bytes=20_000))
                        return True
                    except Exception:
                        continue
    return False

def _starfield_image(dest, seed):
    import random as _r
    from PIL import Image, ImageDraw, ImageFilter
    rnd = _r.Random(seed)
    img = Image.new("RGB", (W, H))
    px = img.load()
    top, bottom = (10, 16, 48), (2, 4, 14)
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
        for x in range(W):
            px[x, y] = row
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
    for _ in range(700):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        b = rnd.choice([110, 150, 190, 230, 255])
        d.point((x, y), fill=(b, b, b))
    for _ in range(50):
        x, y = rnd.randint(2, W - 3), rnd.randint(2, H - 3)
        r = rnd.choice([1, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    img.save(dest, "PNG")
    return True

def gen_image(prompt, dest, seed, query=None):
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
            dest.write_bytes(_http_get(url, timeout=150, min_bytes=15_000))
            log("image from Pollinations")
            return True
        except Exception as e:
            log(f"pollinations attempt {attempt+1}/2 failed: {e}")
            time.sleep(6)
    try:
        _starfield_image(dest, seed)
        log("image = local starfield fallback")
        return True
    except Exception as e:
        log("starfield fallback failed:", e)
        return False

def media_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]).decode().strip()
    return float(out)

KZ_IN  = "z='min(zoom+0.0015,1.15)'"
KZ_OUT = "z='if(eq(on,1),1.15,max(1.001,zoom-0.0021))'"

def make_segment(img, seg, d, zoom_in):
    frames = max(int(d * FPS), FPS)
    z = KZ_IN if zoom_in else KZ_OUT
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"zoompan={z}:d={frames}:s={W}x{H}:fps={FPS},"
          f"eq=brightness=0.0,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", f"{d:.3f}",
                    "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "fast",
                    "-crf", "20", str(seg)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def build_video(image_paths, audio, srt, out_mp4):
    # optional light BGM under narration
    bgm = ROOT / "assets" / "music" / "epic_ambient.mp3"
    if bgm.exists():
        dur = media_duration(audio)
        mixed = WORK / "mixed.mp3"
        fade_end = max(0.1, dur - 2)
        subprocess.run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(bgm), "-i", str(audio),
            "-filter_complex",
            f"[1:a]volume=1.0[n];[0:a]volume=0.10,afade=t=in:st=0:d=2,afade=t=out:st={fade_end:.2f}:d=2[m];"
            f"[n][m]amix=inputs=2:duration=first:dropout_transition=1,loudnorm[a]",
            "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "3", str(mixed)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        audio = mixed

    total = media_duration(audio)
    per = total / len(image_paths)
    segs = []
    for i, img in enumerate(image_paths):
        seg = WORK / f"seg_{i:02d}.mp4"
        make_segment(img, seg, per, zoom_in=(i % 2 == 0))
        segs.append(seg)
        log(f"segment {i+1}/{len(image_paths)} done ({per:.1f}s)")

    concat = WORK / "concat.mp4"
    listfile = WORK / "concat.txt"
    listfile.write_text("\n".join(f"file '{s.as_posix()}'" for s in segs), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-c", "copy", str(concat)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    sub_style = ("FontName=Noto Sans,FontSize=48,Bold=-1,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=4,Outline=3,Shadow=0,MarginV=80")
    subprocess.run(["ffmpeg", "-y", "-i", str(concat), "-i", str(audio),
                    "-vf", f"subtitles={srt.as_posix()}:force_style='{sub_style}'",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_mp4)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("video ready:", out_mp4)

def youtube_upload(ep, mp4, thumbnail=None):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    if not TOKEN_PATH.exists():
        sys.exit("token.json missing - run get_token.py first")
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
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f"upload {int(status.progress() * 100)}%")
    log(f"uploaded: https://youtu.be/{resp['id']}")
    if thumbnail and Path(thumbnail).exists():
        for attempt in range(3):
            try:
                yt.thumbnails().set(videoId=resp["id"],
                                    media_body=MediaFileUpload(str(thumbnail))).execute()
                log("thumbnail set")
                break
            except Exception as e:
                log(f"thumbnail attempt {attempt + 1}/3 failed: {str(e)[:250]}")
                if attempt < 2:
                    time.sleep(20 + attempt * 20)
    add_to_playlist(resp["id"])
    return resp["id"]

def playlist_for():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == PLAYLIST_TITLE:
                return item["id"]
        p = yt.playlists().insert(part="snippet,status",
            body={"snippet": {"title": PLAYLIST_TITLE,
                              "description": "Universe & philosophy shorts — quick cosmic hits.",
            "defaultLanguage": "en" if ENGLISH_MODE else "hi"},
                  "status": {"privacyStatus": "public"}}).execute()
        log(f"created playlist: {PLAYLIST_TITLE} -> {p['id']}")
        return p["id"]
    except Exception as e:
        log("WARNING: playlist lookup failed:", e)
        return None

def add_to_playlist(video_id):
    try:
        pid = playlist_for()
        if not pid:
            return
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yt.playlistItems().insert(part="snippet",
            body={"snippet": {"playlistId": pid,
                              "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        log(f"added to playlist {pid}")
    except Exception as e:
        log("playlist add failed (non-fatal):", e)

def next_episode_id(shorts_count_done):
    return f"{shorts_count_done + 1:03d}"

def main():
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set")

    state = load_state()
    if SHORTS_INDEX:
        ep_id = SHORTS_INDEX
    else:
        ep_id = state["next_id"]

    topic = os.environ.get("SHORTS_TOPIC", "").strip() or random.choice(TOPICS)
    angle = random.choice(ANGLES)
    log(f"short: {ep_id} | topic={topic} | angle={angle}")

    sys_prompt = (
        f"You are a viral YouTube Shorts writer for '{CHANNEL_NAME}', a cosmic deep-dive channel. "
        f"You write SHORT (under 55 seconds) vertical videos in {SHORT_STYLE} "
        "(e.g., 'black hole', 'redshift'). Simple words, short sentences, natural second-person address. You are a master of the first-second hook. "
        "Reply ONLY with valid JSON, no markdown fences."
    )
    user_prompt = f"""Write one vertical YouTube Short in this exact JSON shape:
{{
 "title": "ENGLISH title, max 60 chars, curiosity gap, e.g. 'Why the sky isn't gray at night'",
 "description": "1-2 line hook + 1 subscribe CTA line, max 500 chars. ENGLISH ONLY. Do NOT mention AI, artificial intelligence, or synthetic content.",
 "tags": ["max 10 tags, ENGLISH ONLY"],
 "narration": "~110-130 words of natural Romanized Hindi-Urdu (Latin script, transliterated, e.g. 'doston, universe socha...' - NEVER Devanagari) with English technical terms. Dense, punchy, no fluff. Absolutely MUST open with a hard-hitting hook in the first sentence. End with a thought-provoking question or quote. Do NOT repeat the title verbatim.",
 "image_prompts": ["5 SHORT vertical photorealistic prompts: photorealistic, cinematic, dramatic lighting, ultra detailed, no text, no watermark, <scene description>"],
  "image_queries": ["5 SHORT NASA-image-library search phrases matching the prompts, each 2-4 words, e.g. 'voyager spacecraft', 'webb deep field'. Pure ASCII, no punctuation."],
 "thumbnail_prompt": "one dramatic vertical photorealistic thumbnail prompt, no text, no watermark",
 "thumbnail_hook": "2-4 word ALL-CAPS curiosity hook for the thumbnail, e.g. 'TIME IS A LIE' - English only, no ending period"
}}

Topic: {topic}
Angle: {angle}"""

    raw = call_llm(sys_prompt, user_prompt, max_tokens=3000)
    try:
        ep = extract_json(raw)
    except Exception as e:
        log("JSON parse failed, retrying once:", e)
        raw = call_llm(sys_prompt, user_prompt + "\n\nReply ONLY with valid JSON.", max_tokens=3000)
        ep = extract_json(raw)

    def _has_non_latin_script(text):
        for ch in text:
            o = ord(ch)
            if 0x0900 <= o <= 0x097F or 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
                return True
        return False

    if _has_non_latin_script(ep.get("narration", "")):
        log("narration contains non-Latin script - rewriting in Latin script")
        raw2 = call_llm(sys_prompt,
                        f"Your previous narration contained Devanagari or Urdu characters. Rewrite the SAME short (~110-130 words) STRICTLY in ROMAN/Latin script transliterated Hindi-Urdu (e.g., 'Dosto, sunte ho?') - ZERO Devanagari or Urdu characters, and in {SHORT_STYLE}. Topic: {topic}. Angle: {angle}. Keep it punchy with a hard-hitting hook. Reply ONLY with the narration as plain text.",
                        max_tokens=1500)
        if not _has_non_latin_script(raw2):
            ep["narration"] = raw2.strip()
            log("narration rewritten in Latin script")
        else:
            log("WARNING: rewrite still has non-Latin chars - TTS may fail")

    ep["title"] = scrub_ai_text(ep.get("title", "")) or "Cosmic mystery — watch this"
    ep["description"] = scrub_ai_text(ep.get("description", ""))
    ep["narration"] = ep.get("narration", "").strip()
    log("LLM wrote:", ep["title"])
    log("narration words:", len(ep["narration"].split()))

    prompts = ep["image_prompts"][:N_IMAGES]
    queries = ep.get("image_queries") or []
    image_paths = []
    seed0 = random.randint(1000, 999999)
    for i, p in enumerate(prompts):
        dest = WORK / f"img_{i:02d}.png"
        q = queries[i] if i < len(queries) else None
        if gen_image(p + ", photorealistic, cinematic, vertical, dramatic lighting, ultra detailed, no text, no watermark", dest, seed0 + i, query=q):
            image_paths.append(dest)
        time.sleep(2)
    if len(image_paths) < 3:
        sys.exit(f"only {len(image_paths)} images generated - aborting")

    narration = ep["narration"]
    (WORK / "narration.txt").write_text(narration, encoding="utf-8")

    mp3, srt = WORK / "short.mp3", WORK / "short.srt"
    voices = [VOICE] + [v for v in ("en-IN-NeerjaNeural", "en-IN-PrabhatNeural") if v != VOICE]
    tts_ok = False
    last_err = None
    for voice in voices:
        for attempt in range(2):
            try:
                subprocess.run([sys.executable, "-m", "edge_tts", "--file", str(WORK / "narration.txt"),
                                "--write-media", str(mp3), "--write-subtitles", str(srt),
                                "--voice", voice, f"--rate={TTS_RATE}"], check=True)
                log(f"TTS OK with voice {voice}")
                tts_ok = True
                break
            except subprocess.CalledProcessError as e:
                last_err = e
                log(f"TTS attempt {attempt+1}/2 with {voice} failed ({e}) - retrying")
                time.sleep(5)
        if tts_ok:
            break
    if not tts_ok:
        sys.exit(f"edge-tts failed for every voice; last error: {last_err}")

    out_mp4 = WORK / f"short_{ep_id}.mp4"
    build_video(image_paths, mp3, srt, out_mp4)

    # 16:9 branded thumbnail (crop a centre band out of the first vertical image).
    thumb = None
    try:
        from PIL import Image
        from thumbnail import make_thumbnail, pillar_for
        src = Image.open(image_paths[0]).convert("RGB")
        w, h = src.size
        band_h = int(w * 9 / 16)
        top = max(0, (h - band_h) // 2)
        band = WORK / "thumb_band.jpg"
        src.crop((0, top, w, top + band_h)).save(band, "JPEG", quality=95)
        hook = (ep.get("thumbnail_hook") or "").strip() or ep["title"].split(":")[0][:32].upper()
        pillar = pillar_for(topic + " " + ep["title"])
        thumb = WORK / f"thumb_{ep_id}.jpg"
        make_thumbnail(band, hook, pillar, thumb)
        log(f"thumbnail built (hook='{hook}', pillar={pillar})")
    except Exception as e:
        log("thumbnail build failed (non-fatal):", e)
        thumb = None

    if DRY_RUN or not UPLOAD:
        log("DRY_RUN/UPLOAD=0 - skipping upload. Video at:", out_mp4)
        return

    vid = youtube_upload(ep, out_mp4, thumb)
    mark_done(ep_id)
    log("done -> https://youtu.be/" + vid)

if __name__ == "__main__":
    main()
