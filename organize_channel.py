#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Organize the channel into three pillar playlists.

  COSMOS  -> space, physics, universe
  MIND    -> consciousness, perception, self
  BRAIN   -> psychology, behaviour, emotion

Long videos are classified by title keywords and added to their pillar
playlist (they stay in the existing "Deep Dives" playlist too, so nothing
is lost). Shorts are left in the shorts playlist.

Usage:
  python organize_channel.py            # dry run, prints the plan
  python organize_channel.py --apply    # creates playlists and adds videos
"""
import argparse
import re
import sys
import time
from pathlib import Path

from thumbnail import pillar_for

ROOT = Path(__file__).resolve().parent
TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

PLAYLISTS = {
    "cosmos": ("Cosmos Files", "Deep dives into black holes, galaxies, quantum physics and the origin of the universe."),
    "mind":   ("The Mind Files", "Consciousness, perception and the self - where neuroscience meets philosophy."),
    "brain":  ("Brain Traps", "Psychology, biases and the hidden machinery of everyday decisions."),
}


def log(*a):
    print(*a, flush=True)


def duration_seconds(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    items, token = [], None
    while True:
        r = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=token).execute()
        items += r["items"]
        token = r.get("nextPageToken")
        if not token:
            break
    log(f"uploads: {len(items)}")

    vids = [i["contentDetails"]["videoId"] for i in items]
    meta = {}
    for i in range(0, len(vids), 50):
        r = yt.videos().list(part="snippet,contentDetails",
                             id=",".join(vids[i:i + 50])).execute()
        for v in r["items"]:
            meta[v["id"]] = (v["snippet"]["title"],
                             duration_seconds(v["contentDetails"]["duration"]))

    buckets = {"cosmos": [], "mind": [], "brain": [], "short": []}
    for vid, (title, dur) in meta.items():
        if dur <= 65:
            buckets["short"].append((vid, title))
        else:
            buckets[pillar_for(title)].append((vid, title))

    for k in ("cosmos", "mind", "brain"):
        log(f"\n{k.upper()} ({len(buckets[k])}):")
        for vid, title in buckets[k]:
            log(f"  {vid}  {title[:70]}")
    log(f"\nshorts skipped: {len(buckets['short'])}")

    if not a.apply:
        log("\n(dry run - pass --apply to create playlists and add videos)")
        return

    existing = {p["snippet"]["title"]: p["id"]
                for p in yt.playlists().list(part="snippet", mine=True,
                                             maxResults=50).execute().get("items", [])}

    for key, (title, desc) in PLAYLISTS.items():
        pid = existing.get(title)
        if not pid:
            p = yt.playlists().insert(
                part="snippet,status",
                body={"snippet": {"title": title, "description": desc,
                                  "defaultLanguage": "en"},
                      "status": {"privacyStatus": "public"}}).execute()
            pid = p["id"]
            log(f"created playlist: {title} -> {pid}")
        else:
            log(f"playlist exists: {title} -> {pid}")

        have = set()
        tok = None
        for attempt in range(5):
            try:
                while True:
                    r = yt.playlistItems().list(part="contentDetails", playlistId=pid,
                                                maxResults=50, pageToken=tok).execute()
                    for it in r["items"]:
                        have.add(it["contentDetails"]["videoId"])
                    tok = r.get("nextPageToken")
                    if not tok:
                        break
                break
            except Exception as e:
                if "playlistNotFound" in str(e) and attempt < 4:
                    log("  playlist not visible yet, retrying in 5s ...")
                    time.sleep(5)
                    tok = None
                    continue
                raise

        added = 0
        for vid, _ in buckets[key]:
            if vid in have:
                continue
            for attempt in range(4):
                try:
                    yt.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": pid,
                                          "resourceId": {"kind": "youtube#video",
                                                         "videoId": vid}}}).execute()
                    added += 1
                    break
                except Exception as e:
                    msg = str(e)
                    if ("playlistNotFound" in msg or "videoNotFound" in msg) and attempt < 3:
                        time.sleep(5)
                        continue
                    log(f"  add failed {vid}: {msg[:160]}")
                    break
        log(f"  added {added} new video(s) to {title}")


if __name__ == "__main__":
    main()
