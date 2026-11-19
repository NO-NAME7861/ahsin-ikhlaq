#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weekly security audit for the Channel pipeline.

Runs on the CI runner. Reads token.json (from YOUTUBE_TOKEN_JSON secret).
Checks:
  1. Token works — videos.list uploads playlist (1 quota unit)
  2. State file unchanged for >7 days (no upload this week => suspicious)
  3. Repo has no accidental secrets committed (basic heuristic scan)

Exit codes:
  0 = all good
  1 = security/health issue (workflow fails, GitHub emails the owner)
"""
import json, os, re, sys, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "episodes.json"
PROBLEMS = []

def log(msg):
    print(f"[security] {msg}", flush=True)

def ok(msg):
    log("OK  " + msg)

def warn(msg):
    PROBLEMS.append(msg)
    log("WARN " + msg)

# ---- 1. Token works --------------------------------------------------------
TOKEN = ROOT / "token.json"
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
    log(f"token valid — channel: {ch['snippet']['title']} | subs: {ch['statistics'].get('subscriberCount')}")
    ok("YouTube API token works")
except Exception as e:
    warn(f"YouTube API token check failed ({type(e).__name__}: {e}) — refresh token may be expired; check YOUTUBE_TOKEN_JSON secret on Monday morning")

# ---- 2. State file freshness ------------------------------------------------
try:
    mtime = STATE.stat().st_mtime
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)
    if age > timedelta(days=8):
        warn(f"episodes.json unchanged for {age.days} days — no upload this week (check the 8 PM schedule)")
    else:
        ok(f"state file fresh (updated {age.days}d ago)")
    data = json.loads(STATE.read_text(encoding="utf-8"))
    log(f"done={len(data.get('done', []))} next={data.get('next_id')}")
except Exception as e:
    warn(f"state file problem: {e}")

# ---- 3. Secret scan (heuristic) ----------------------------------------------
# Patterns look for leaked access tokens and Google OAuth URLs with embedded keys.
SECRET_PATTERNS = [
    re.compile(r"ya29\.[a-zA-Z0-9_-]{40,}"),          # Google OAuth access token
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),            # Google API key
    re.compile(r"Bearer\s+ya29\."),                    # Bearer header on OAuth token
    re.compile(r"refresh_token\"\s*:\s*\"[0-9a-f]"),    # refresh token in JSON
    re.compile(r"client_secret\"\s*:\s*\"[0-9a-fA-F]"), # refresh token snippet
]
tracked = subprocess.check_output(["git", "ls-files"], cwd=str(ROOT),
                                  text=True).splitlines()
# files we already know hold example/safe structures (gitignore patterns end with .py scripts that
# reference env values only). Skip large binary files.
BINARY_EXTENSIONS = {".mp3", ".png", ".jpg", ".jpeg", ".mp4", ".webp", ".zip", ".otf", ".ttf"}
leaks = 0
for rel in tracked:
    p = ROOT / rel
    if p.suffix.lower() in BINARY_EXTENSIONS:
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            warn(f"secret-looking string in {rel}")
            leaks += 1
if leaks == 0:
    ok("no leaked secrets in tracked files")

# ---- 4. Summary --------------------------------------------------------------
log(f"checks complete: {len(PROBLEMS)} issue(s)")
if PROBLEMS:
    for p in PROBLEMS:
        print(f"::warning::{p}")
    sys.exit(1)
print("all security checks passed")
