#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retrofit branded thumbnails onto already-published videos.

Reads a JSON plan:
[
  {"id": "VIDEO_ID", "hook": "WHERE IS EVERYONE?", "pillar": "cosmos",
   "prompt": "pollinations image prompt", "base": "optional/local/base.jpg"}
]

For each entry it:
  1. uses `base` if given, else generates a new 1280x720 base via Pollinations
     (4 attempts), else falls back to the current YouTube thumbnail,
  2. composes the branded thumbnail (thumbnail.make_thumbnail),
  3. uploads it with yt.thumbnails().set (3 attempts).

Usage:
  python retrofit_thumbs.py --plan plan.json [--dry-run]
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from thumbnail import make_thumbnail

ROOT = Path(__file__).resolve().parent
TOKEN = ROOT / "token.json"
WORK = ROOT / "work" / "retrofit"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def log(*a):
    print(*a, flush=True)


def fetch(url, timeout=150):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < 15_000:
        raise RuntimeError(f"image too small ({len(data)} bytes)")
    return data


def pollinations(prompt, seed, dest):
    for attempt in range(4):
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
               + f"?width=1280&height=720&nologo=true&seed={seed + attempt}")
        try:
            dest.write_bytes(fetch(url))
            return True
        except Exception as e:
            log(f"    pollinations {attempt + 1}/4 failed: {e}")
            time.sleep(10 + attempt * 5)
    return False


def current_thumb(video_id, dest):
    for name in ("maxresdefault", "sddefault", "hqdefault"):
        try:
            dest.write_bytes(fetch(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"))
            log(f"    base = existing YouTube {name}")
            return True
        except Exception:
            continue
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)

    yt = None
    if not a.dry_run:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ok, failed = [], []
    for item in plan:
        vid = item["id"]
        hook = item["hook"]
        pillar = item.get("pillar", "cosmos")
        log(f"\n[{vid}] {hook}  ({pillar})")

        base = WORK / f"base_{vid}.jpg"
        out = WORK / f"thumb_{vid}.jpg"

        if item.get("base") and Path(item["base"]).exists():
            base.write_bytes(Path(item["base"]).read_bytes())
            log("    base = provided file")
        elif not (base.exists() and base.stat().st_size > 15_000):
            if not pollinations(item.get("prompt") or item.get("title", hook), hash(vid) % 9000, base):
                log("    falling back to current YouTube thumbnail")
                if not current_thumb(vid, base):
                    log("    NO BASE IMAGE - skipping")
                    failed.append(vid)
                    continue

        make_thumbnail(base, hook, pillar, out)
        log(f"    composed {out.name} ({out.stat().st_size // 1024} KB)")

        if a.dry_run:
            ok.append(vid)
            continue

        for attempt in range(3):
            try:
                yt.thumbnails().set(videoId=vid,
                                    media_body=MediaFileUpload(str(out))).execute()
                log("    thumbnail SET")
                ok.append(vid)
                break
            except Exception as e:
                log(f"    set attempt {attempt + 1}/3 failed: {str(e)[:250]}")
                if attempt < 2:
                    time.sleep(20 + attempt * 20)
        else:
            failed.append(vid)

        time.sleep(3)

    log(f"\nDONE ok={len(ok)} failed={len(failed)}")
    if failed:
        log("failed ids:", ", ".join(failed))


if __name__ == "__main__":
    main()
