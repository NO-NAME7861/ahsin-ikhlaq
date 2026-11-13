#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ahsin Akhlaq — Universe & Philosophy Automation
Pipeline: LLM script (expert-level cosmology + philosophy, Urdu + English terms)
          -> photorealistic images -> edge-tts ur-PK voice
          -> 1024x576 video (Ken Burns + subtitles) -> YouTube upload -> Drive backup
Run locally (test):  DRY_RUN=1 python generate_episode.py
Run in CI:           private run first, then set UPLOAD=1
"""
import os, sys, json, csv, time, random, base64, asyncio, subprocess
import re
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

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
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
] ]
VOICE              = os.environ.get("TTS_VOICE", "ur-PK-UzmaNeural")   # Urdu female voice
TTS_RATE           = os.environ.get("TTS_RATE", "-5%")
PRIVACY_STATUS     = os.environ.get("PRIVACY_STATUS", "private")  # safe default; set public when confident
UPLOAD             = os.environ.get("UPLOAD", "1") == "1"
DRY_RUN            = os.environ.get("DRY_RUN", "0") == "1"
EPISODE_OVERRIDE   = os.environ.get("EPISODE_INDEX", "").strip()  # force a specific episode id

TARGET_MINUTES     = int(os.environ.get("TARGET_MINUTES", "12"))   # minutes; <=14 keeps videos under the 15-minute upload limit for unverified channels. Raise via vars after phone verification (youtube.com/verify).
WORDS_TARGET       = int(os.environ.get("WORDS_TARGET", str(TARGET_MINUTES * 145)))
LONG_MODE          = TARGET_MINUTES >= 15
W, H, FPS = 1024, 576, 25
_n_img_env = os.environ.get("N_IMAGES", "").strip()
N_IMAGES           = int(_n_img_env) if _n_img_env else (20 if LONG_MODE else 16)
CHANNEL_NAME = "Ahsin Akhlaq"

# ---------------------------------------------------------------- helpers

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

def load_episode():
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

def call_llm(row):
    sys_prompt = (
        f"You are a world-class science communicator and philosopher writing for the YouTube channel '{CHANNEL_NAME}', "
        "a deep-dive channel that merges cutting-edge universe exploration and space science with profound philosophy. "
        "You combine the rigor of a cosmology textbook, the storytelling of Carl Sagan, and the depth of a philosophy "
        "seminar. You write for a Pakistani and Urdu-speaking audience in expert-level Urdu: the narration is written "
        "in Urdu script (Nastaliq) with English technical terms left in Latin script (e.g., 'black hole', 'entropy', "
        "'dark matter', 'fine-tuning'). You NEVER use Devanagari/Hindi. You NEVER fabricate facts: use real missions (Voyager, JWST, LIGO, "
        "Event Horizon Telescope, New Horizons), real scientists (Einstein, Sagan, Hawking, Noether), real theories, real "
        "numbers and dates. If a fact is uncertain or debated, say so honestly. "
        "Never use phrases like 'AI-generated', 'AI content', 'AI narration', or 'artificial intelligence' in the title or description. "
        "Reply ONLY with valid JSON, no markdown fences."
    )
    n_img_prompts = N_IMAGES
    user_prompt = f"""Write one complete deep-dive episode in this exact JSON shape:
{{
 "title": "YouTube title, max 70 chars, expert curiosity-gap ENGLISH ONLY, e.g. 'What Happens Inside a Black Hole? The Information Paradox Explained'",
 "description": "2-3 sentence hook + 1 line central insight + line: 'Sources: NASA, ESA, peer-reviewed journals.' + subscribe CTA, max 1000 chars. ENGLISH ONLY. Do NOT mention AI, artificial intelligence, AI-generated visuals, AI narration, or synthetic content.",
 "tags": ["max 15 tags, ENGLISH ONLY"],
 "moral": "one sentence — the episode's central philosophical insight",
 "narration": "{WORDS_TARGET} words (±10%) continuous narration in expert-level Urdu with English technical terms in Latin script. WRITTEN IN URDU SCRIPT (Nastaliq) with English technical terms in Latin script (such as: 'black hole', 'redshift', 'entropy'). Natural spoken rhythm: short sentences, you-voice, rhetorical questions, breath-catching pauses. Split into 6-10 scenes (separated by paragraph breaks) so viewers never feel a dull moment. Each scene: a precise scientific fact/mechanism -> its deeper meaning -> a philosophical question it raises. Include REAL numbers, names, dates. MUST end with the central philosophical insight. Speak like a brilliant, warm storyteller who reads cosmology papers for a living.",
 "image_prompts": ["{n_img_prompts} SHORT prompts, each: photorealistic, cinematic, dramatic lighting, ultra detailed, no text, no watermark, <scene description: e.g. 'interior of an accretion disk around a supermassive black hole seen from a nearby camera, gravitational lensing, photon ring'>. Use space imagery: nebulae, exoplanets, observatories, astronauts, planet surfaces, deep field images, star clusters."],
 "thumbnail_prompt": "one dramatic photorealistic prompt for a 16:9 thumbnail, high contrast, no text, no watermark"
}}

Episode brief (topic + central insight):
Topic seed: {row['topic']}
Central insight: {row['moral']}"""

    if LONG_MODE:
        ep = call_llm_long(row, sys_prompt, user_prompt)
        log("LLM OK via long-form mode (3 narrations stitched)")
        return ep

    return _llm_with_fallback(sys_prompt, user_prompt, 8000, "episode")

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
    meta_prompt = f"""Write ONLY the metadata for one long-form (50-minute) deep-dive episode. Reply with valid JSON:
{{
 "title": "YouTube title, max 70 chars, expert curiosity-gap ENGLISH ONLY",
 "description": "2-3 sentence hook + 1 line central insight + line: 'Sources: NASA, ESA, peer-reviewed journals.' + subscribe CTA, max 1000 chars. ENGLISH ONLY. Do NOT mention AI, artificial intelligence, AI-generated visuals, AI narration, or synthetic content.",
 "tags": ["max 15 tags, ENGLISH ONLY"],
 "moral": "one sentence — the episode's central philosophical insight",
 "image_prompts": ["{N_IMAGES} SHORT prompts, each: photorealistic, cinematic, dramatic lighting, ultra detailed, no text, no watermark, <scene description>. Space imagery throughout."],
 "thumbnail_prompt": "one dramatic photorealistic prompt for a 16:9 thumbnail, high contrast, no text, no watermark",
 "outline": ["8 scene summaries with the key scientific facts, numbers and philosophers to cover, in order — this is the plan for the 3 narrative parts"]
}}

Topic seed: {row['topic']}
Central insight: {row['moral']}"""
    meta = _llm_with_fallback(sys_prompt, meta_prompt, 4500, "meta")
    outline = meta.get("outline", [])
    outline_txt = "\n".join(f"Scene {i+1}: {o}" for i, o in enumerate(outline))

    parts = []
    for part_no in (1, 2, 3):
        part_prompt = f"""You are writing PART {part_no} of 3 narration parts for ONE 50-minute deep-dive episode
(target total {WORDS_TARGET} words; this part MUST be ~{WORDS_TARGET // 3} words (±10%), expert-level Urdu with English technical terms in Latin script, natural spoken rhythm, paragraph breaks every few sentences).

Episode topic: {row['topic']}
Central insight: {row['moral']}

FULL OUTLINE (do NOT repeat what other parts cover — write ONLY your assigned scenes):
{outline_txt}

PART {part_no} ASSIGNMENT:
{'Open the episode with a powerful hook. Cover outline scenes 1-3. End part 1 on a cliffhanger.' if part_no == 1 else ('Continue from part 1. Cover outline scenes 4-6. Keep tension rising. End part 2 mid-crescendo.' if part_no == 2 else 'Now land the plane. Cover the remaining outline scenes. End with the central philosophical insight, delivered with awe.')}

Reply with plain text ONLY (no JSON, no markdown) - just the narration in Urdu script with English terms in Latin script, ready for voiceover."""
        part = _llm_with_fallback(sys_prompt, part_prompt, 6000, f"narration-part-{part_no}", expect_json=False)
        parts.append(part.strip())

    ep = dict(meta)
    ep.pop("outline", None)
    ep["narration"] = "\n\n".join(p.strip() for p in parts)
    wc = len(ep["narration"].split())
    log(f"long-form narration assembled: {wc} words")
    if wc < WORDS_TARGET * 0.6:
        log("WARNING: narration shorter than expected — video may be shorter than target")
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

def _pollinations_image(prompt, dest, seed):
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + f"?width={W}&height={H}&nologo=true&seed={seed}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if len(data) <= 20_000:
        raise RuntimeError(f"pollinations too small: {len(data)} bytes")
    dest.write_bytes(data)
    return True

def gen_image(prompt, dest, seed):
    for attempt in range(3):
        try:
            url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
                   + f"?width={W}&height={H}&nologo=true&seed={seed}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) > 15_000:
                dest.write_bytes(data)
                return True
            raise RuntimeError("pollinations too small")
        except Exception as e:
            backoff = [12, 25, 45][min(attempt, 2)]
            log(f"image retry {attempt + 1}/3 (waiting {backoff}s): {e}")
            time.sleep(backoff)
    log("WARNING: image failed after retries:", prompt[:60])
    return False

# ---------------------------------------------------------------- 3. voice

def run_tts(text_file, mp3, srt):
    cmd = [sys.executable, "-m", "edge_tts", "--file", str(text_file),
           "--write-media", str(mp3), "--write-subtitles", str(srt),
           "--voice", VOICE, f"--rate={TTS_RATE}"]
    subprocess.run(cmd, check=True)

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
           "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "ultrafast",
           "-crf", "27", str(seg)]
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
        f"[1:a]volume=1.0[n];[0:a]volume=0.16,"
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

    sub_style = ("FontName=Noto Nastaliq Urdu,FontSize=16,Bold=-1,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=4,Outline=2,Shadow=0,MarginV=22")
    subprocess.run(["ffmpeg", "-y", "-i", str(concat), "-i", str(audio),
                    "-vf", f"subtitles={srt.as_posix()}:force_style='{sub_style}'",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_mp4)],
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
            "defaultLanguage": "hi",
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(mp4), chunksize=16 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    log("uploading to YouTube ...")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f"upload {int(status.progress() * 100)}%")
    vid = resp["id"]
    log(f"uploaded: https://youtu.be/{vid}")

    if thumbnail and Path(thumbnail).exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
            log("thumbnail set")
        except Exception as e:
            log("thumbnail set skipped (channel likely lacks custom thumbnail permission):", e)
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

def playlist_for():
    """Return the playlist ID, creating the playlist if missing."""
    if PLAYLIST_ID:
        return PLAYLIST_ID
    title = PLAYLIST_TITLE
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
        desc = ("Universe exploration and philosophy deep dives. "
                "Every episode explores one profound question about the cosmos and the human condition.")
        p = yt.playlists().insert(part="snippet,status",
            body={"snippet": {"title": title, "description": desc, "defaultLanguage": "hi"},
                  "status": {"privacyStatus": "public"}}).execute()
        log(f"created playlist: {title} -> {p['id']}")
        return p["id"]
    except Exception as e:
        log("WARNING: playlist lookup failed:", e)
        return None

def add_to_playlist(video_id):
    pid = playlist_for()
    if not pid:
        log("no playlist id - skipping playlist add")
        return
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        yt.playlistItems().insert(part="snippet",
            body={"snippet": {"playlistId": pid,
                              "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        log(f"added to playlist {pid}")
    except Exception as e:
        log("playlist add failed (non-fatal):", e)

# ---------------------------------------------------------------- main

IMAGE_SUFFIX = (", photorealistic, cinematic, dramatic lighting, ultra detailed, "
                "documentary style, no text, no watermark")
THUMB_SUFFIX = (", photorealistic, cinematic, dramatic, high contrast, no text, no watermark")

def main():
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set")

    row = load_episode()
    log(f"episode: {row['id']} | {row['topic']}")

    ep = call_llm(row)
    ep["title"] = scrub_ai_text(ep.get("title", ""))
    ep["description"] = scrub_ai_text(ep.get("description", ""))
    log("LLM wrote:", ep["title"])
    (WORK / "episode.json").write_text(json.dumps(ep, indent=2, ensure_ascii=False))

    narration = ep["narration"]
    (WORK / "narration.txt").write_text(narration, encoding="utf-8")
    log(f"narration words: {len(narration.split())}")

    prompts = ep["image_prompts"][:N_IMAGES]
    image_paths = []
    seed0 = random.randint(1000, 999999)
    for i, p in enumerate(prompts):
        dest = WORK / f"img_{i:02d}.png"
        if gen_image(p + IMAGE_SUFFIX, dest, seed0 + i):
            image_paths.append(dest)
        time.sleep(4)
    if len(image_paths) < 8:
        sys.exit(f"only {len(image_paths)} images generated - aborting")

    mp3, srt = WORK / "narration.mp3", WORK / "narration.srt"
    run_tts(WORK / "narration.txt", mp3, srt)

    thumb = WORK / "thumb.png"
    gen_image(ep.get("thumbnail_prompt", prompts[0]) + THUMB_SUFFIX, thumb, seed0 + 999)

    out_mp4 = WORK / f"episode_{row['id']}.mp4"
    build_video(image_paths, mp3, srt, out_mp4, thumb)

    if DRY_RUN or not UPLOAD:
        log("DRY_RUN/UPLOAD=0 - skipping upload. Video at:", out_mp4)
        return

    vid = youtube_upload(ep, out_mp4, thumb)
    add_to_playlist(vid)
    try:
        drive_backup(out_mp4)
    except Exception as e:
        log("drive backup failed (non-fatal):", e)
    mark_done(row["id"])
    log("done -> https://youtu.be/" + vid)

if __name__ == "__main__":
    main()
