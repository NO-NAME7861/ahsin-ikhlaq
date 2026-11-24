#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weekly learning check for the channel pipeline.

Reads the channel's recent uploads from YouTube (READ-ONLY), groups them by
pillar (COSMOS / MIND / BRAIN) and by format (long / Shorts), then writes
state/learning.json with:

  - per-pillar performance (count, total, mean, median views)
  - best and worst recent videos
  - concrete "lessons" that quality.py injects into the next prompt

The point is a closed loop: what the audience rewards this week shapes the
script the pipeline writes next week.
"""
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEARN = ROOT / "state" / "learning.json"
TOKEN = ROOT / "token.json"

RECENT = 50  # look at the last 50 uploads


def log(msg):
    print(f"[learn] {msg}", flush=True)


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def stats(values):
    if not values:
        return {"n": 0, "total": 0, "mean": 0.0, "median": 0.0, "max": 0}
    return {
        "n": len(values),
        "total": sum(values),
        "mean": round(statistics.mean(values), 1),
        "median": statistics.median(values),
        "max": max(values),
    }


def main():
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from thumbnail import pillar_for
    except Exception as e:
        log(f"FATAL: imports failed: {e}")
        sys.exit(1)

    try:
        SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        log(f"FATAL: token not usable: {e}")
        sys.exit(1)

    ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    items, tok = [], None
    while len(items) < RECENT:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=tok).execute()
        items += r["items"]
        tok = r.get("nextPageToken")
        if not tok:
            break
    ids = [i["contentDetails"]["videoId"] for i in items[:RECENT]]

    rows = []
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,statistics,contentDetails",
                                id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            dur = secs(v["contentDetails"]["duration"])
            title = v["snippet"]["title"]
            rows.append({
                "id": v["id"],
                "title": title,
                "views": int(v["statistics"].get("viewCount", 0)),
                "likes": int(v["statistics"].get("likeCount", 0)),
                "comments": int(v["statistics"].get("commentCount", 0)),
                "published": v["snippet"]["publishedAt"][:10],
                "seconds": dur,
                "format": "short" if dur <= 65 else "long",
                "pillar": pillar_for(title),
            })

    if len(rows) < 5:
        log(f"only {len(rows)} videos - not enough data to learn")
        sys.exit(0)

    longs = [r for r in rows if r["format"] == "long"]
    shorts = [r for r in rows if r["format"] == "short"]
    per_pillar = {}
    for name in ("cosmos", "mind", "brain"):
        bucket = [r for r in rows if r["format"] == "long" and r["pillar"] == name]
        per_pillar[name] = stats([r["views"] for r in bucket])

    top = sorted(rows, key=lambda r: r["views"], reverse=True)[:5]
    bottom = sorted(rows, key=lambda r: r["views"])[:5]
    zero = [r for r in rows if r["views"] == 0]

    lessons = []
    lp, ls = stats([r["views"] for r in longs]), stats([r["views"] for r in shorts])
    if ls["mean"] and lp["mean"] and ls["mean"] > lp["mean"] * 1.5:
        lessons.append(
            f"Shorts average {ls['mean']} views vs {lp['mean']} for long videos - "
            "keep 3 Shorts/day and make every Short share the day's long-video topic."
        )

    ranked = sorted(per_pillar.items(), key=lambda kv: kv[1]["mean"], reverse=True)
    best_name, best = ranked[0]
    worst_name, worst = ranked[-1]
    if best["n"] >= 2 and worst["n"] >= 2 and best["mean"] > worst["mean"] * 1.25:
        lessons.append(
            f"{best_name.upper()} averages {best['mean']} views vs {worst_name.upper()} "
            f"{worst['mean']} - lead with a {best_name} angle in the title and thumbnail hook."
        )

    if zero:
        lessons.append(
            f"{len(zero)} recent videos have 0 views - re-check their thumbnails, "
            "titles and whether they were ever shown in recommendations."
        )

    top3 = top[:3]
    if sum(1 for r in top3 if "?" in r["title"]) >= 2:
        lessons.append("Question titles dominate the top 3 - put the core question in the title.")
    if sum(1 for r in top3 if len(r["title"]) <= 55) >= 2:
        lessons.append("Top performers use short titles (under 55 characters) - keep it tight.")

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel": {
            "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
            "views": int(ch["statistics"].get("viewCount", 0)),
            "videos": int(ch["statistics"].get("videoCount", 0)),
        },
        "sample_size": len(rows),
        "long": lp,
        "shorts": ls,
        "per_pillar": per_pillar,
        "top_performers": [{"id": r["id"], "views": r["views"], "title": r["title"]} for r in top],
        "bottom_performers": [{"id": r["id"], "views": r["views"], "title": r["title"]} for r in bottom],
        "zero_view": [{"id": r["id"], "title": r["title"]} for r in zero],
        "lessons": lessons,
        "per_video": {r["id"]: {k: r[k] for k in
                                ("title", "views", "likes", "comments", "published",
                                 "format", "pillar")} for r in rows},
    }

    LEARN.parent.mkdir(parents=True, exist_ok=True)
    LEARN.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    log(f"sample: {len(rows)} videos ({len(longs)} long / {len(shorts)} shorts)")
    for name, s in per_pillar.items():
        log(f"  {name.upper():6s} n={s['n']:3d} mean={s['mean']:6.1f} median={s['median']:4.0f}")
    log(f"top: " + ", ".join(f"{r['views']}v {r['title'][:40]}" for r in top[:3]))
    for lesson in lessons:
        log(f"lesson: {lesson}")
    log("wrote state/learning.json")


if __name__ == "__main__":
    main()
