#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weekly learning check for the channel pipeline.

Pulls view counts for recent episodes from YouTube, computes a simple
"what's working" report, and writes state/learning.json.

This is READ-ONLY for YouTube — it only reads video statistics.
"""
import json, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "episodes.json"
LEARN = ROOT / "state" / "learning.json"
TOKEN = ROOT / "token.json"

def log(msg):
    print(f"[learn] {msg}", flush=True)

def main():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"FATAL: could not load episodes.json: {e}")
        sys.exit(1)

    done = state.get("done", [])
    if len(done) < 3:
        log("only %d done episodes — not enough data to learn" % len(done))
        sys.exit(0)

    # take the last 10 done episodes — these are the freshest signals
    sample = done[-10:]
    log(f"checking views for: {sample}")

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"FATAL: token not usable: {e}")
        sys.exit(1)

    resp = yt.videos().list(part="snippet,statistics", id=",".join(sample)).execute()
    by_id = {v["id"]: v for v in resp.get("items", [])}
    titles = {}
    for r in sample:
        v = by_id.get(r)
        if v:
            titles[r] = {
                "title": v["snippet"]["title"],
                "views": int(v["statistics"].get("viewCount", 0)),
                "likes": int(v["statistics"].get("likeCount", 0)),
                "comments": int(v["statistics"].get("commentCount", 0)),
            }
        else:
            titles[r] = {"title": None, "views": 0, "likes": 0, "comments": 0, "missing": True}

    total_views = sum(t["views"] for t in titles.values() if t)
    top = sorted(titles.items(), key=lambda kv: kv[1]["views"], reverse=True)[:3]
    bottom = sorted(titles.items(), key=lambda kv: kv[1]["views"])[:3]

    new_learning = {
        "sample_size": len(sample),
        "total_views": total_views,
        "per_video": titles,
        "top_performers": [{"id": k, "views": v["views"], "title": v["title"]} for k, v in top],
        "bottom_performers": [{"id": k, "views": v["views"], "title": v["title"]} for k, v in bottom],
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    LEARN.parent.mkdir(parents=True, exist_ok=True)
    LEARN.write_text(json.dumps(new_learning, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    log("wrote state/learning.json")
    log(f"top performers: " + ", ".join(f"{k}={v['views']}" for k, v in top))

if __name__ == "__main__":
    main()
