#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok cross-posting for Ahsin Akhlaq.

Uses the TikTok Content Posting API (business-api.tiktokapis.com) to publish
the freshly uploaded long video to TikTok, best-effort:

  POST /post/publish/video/init/    -> publish_id
  POST /post/publish/video/publish/ -> publish by publish_id
  GET  /post/publish/status/        -> status

Requires:
  - A TikTok developer app with Content Posting API permission
    (https://developers.tiktok.com -> Apps -> Create app -> Content Posting)
  - User access token in env: TIKTOK_ACCESS_TOKEN (or tiktok_token.json)

If the token is missing or any call fails, this is a non-fatal no-op - the
YouTube upload is the source of truth.
"""
import os
import time

import requests

TIKTOK_INIT = "https://business-api.tiktokapis.com/post/publish/video/init/"
TIKTOK_PUBLISH = "https://business-api.tiktokapis.com/post/publish/video/publish/"
TIKTOK_STATUS = "https://business-api.tiktokapis.com/post/publish/status/"

ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()


def log(msg):
    print(f"[tiktok] {msg}", flush=True)


def _headers():
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


def upload(video_path, title, description=""):
    """Publish `video_path` on TikTok. Returns TikTok publish id or None."""
    if not ACCESS_TOKEN:
        log("TIKTOK_ACCESS_TOKEN not set - skipping TikTok cross-post")
        return None
    try:
        r = requests.post(TIKTOK_INIT, headers=_headers(), json={
            "access_token": ACCESS_TOKEN,
            "post_mode": "PUBLISH",
            "post_info": {"title": (title or "")[:2200]},
        }, timeout=30)
        r.raise_for_status()
        publish_id = (r.json().get("data") or {}).get("publish_id")
        if not publish_id:
            log(f"TikTok init returned no publish_id: {str(r.json())[:300]}")
            return None
        log(f"TikTok publish_id: {publish_id}")
        r2 = requests.post(TIKTOK_PUBLISH, headers=_headers(),
                           json={"access_token": ACCESS_TOKEN, "publish_id": publish_id},
                           timeout=60)
        r2.raise_for_status()
        log(f"TikTok publish call ok: {str(r2.json())[:300]}")
        time.sleep(10)
        r3 = requests.get(TIKTOK_STATUS, headers=_headers(),
                          params={"access_token": ACCESS_TOKEN, "publish_id": publish_id},
                          timeout=30)
        r3.raise_for_status()
        log(f"TikTok status: {str(r3.json())[:300]}")
        return publish_id
    except Exception as e:
        log(f"TikTok cross-post failed (non-fatal, YouTube untouched): {e}")
        return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    a = ap.parse_args()
    log(f"publishing {a.video} -> {a.title}")
    print("publish_id:", upload(a.video, a.title, a.description))
