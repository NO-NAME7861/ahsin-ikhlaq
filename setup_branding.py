#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate and apply channel branding:
  - 2560x1440 banner (safe-area text)
  - 150x150 watermark
  - channel title / description / keywords

Usage:
  python setup_branding.py            # generate images only
  python setup_branding.py --apply    # generate + upload to YouTube
"""
import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

ACCENTS = [(56, 189, 248), (167, 139, 250), (251, 146, 60)]  # cosmos / mind / brain

TITLE = "Ahsin Akhlaq"
DESCRIPTION = (
    "Ahsin Akhlaq - Universe + Mind.\n\n"
    "One channel, three journeys:\n"
    "\U0001F30C COSMOS - black holes, galaxies, quantum physics, the origin of the universe\n"
    "\U0001F9E0 MIND - consciousness, perception and the self\n"
    "\U0001F9E9 BRAIN - psychology, biases and the hidden machinery of decisions\n\n"
    "Every video starts with one question and follows the real science, philosophy "
    "and psychology behind it. Facts are grounded in NASA, ESA and peer-reviewed research.\n\n"
    "New deep dives daily. Shorts for the quick hit."
)
KEYWORDS = ("universe space black holes consciousness psychology philosophy "
            "science documentary astronomy neuroscience mind cosmic quantum physics")


def _font(size):
    for p in ("C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_banner(path):
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H))
    px = img.load()
    top, bottom = (7, 10, 26), (14, 20, 48)
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3))
        for x in range(W):
            px[x, y] = row

    rnd = random.Random(11)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for cx, cy, rx, ry, col in [
        (520, 380, 700, 420, (30, 70, 160)),
        (2050, 1050, 800, 480, (90, 40, 140)),
        (1300, 200, 600, 300, (20, 90, 130)),
    ]:
        gd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 0.55)

    d = ImageDraw.Draw(img)
    for _ in range(700):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        b = rnd.choice([70, 110, 150, 200, 255])
        d.point((x, y), fill=(b, b, b))
    for _ in range(60):
        x, y = rnd.randint(4, W - 5), rnd.randint(4, H - 5)
        r = rnd.choice([1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))

    # safe area is 1235x338 centred; keep all text inside it
    f_title = _font(150)
    f_sub = _font(46)
    title = "AHSIN AKHLAQ"
    sub = "U N I V E R S E   \u00b7   M I N D   \u00b7   P S Y C H O L O G Y"
    tw = d.textlength(title, font=f_title)
    sw = d.textlength(sub, font=f_sub)
    ty, sy = 560, 770
    d.text(((W - tw) / 2, ty), title, font=f_title, fill=(255, 255, 255))
    d.text(((W - sw) / 2, sy), sub, font=f_sub, fill=(210, 218, 240))

    # three accent bars under the tagline
    bar_w, gap, y = 150, 26, 840
    total = bar_w * 3 + gap * 2
    x = (W - total) / 2
    for col in ACCENTS:
        d.rounded_rectangle([x, y, x + bar_w, y + 10], radius=5, fill=col)
        x += bar_w + gap

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    print("banner ->", path, f"{W}x{H}")


def make_watermark(path):
    S = 150
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, S - 4, S - 4], fill=(8, 11, 24, 235))
    d.ellipse([4, 4, S - 4, S - 4], outline=(56, 189, 248, 255), width=5)
    f = _font(62)
    txt = "AA"
    tw = d.textlength(txt, font=f)
    d.text(((S - tw) / 2, 40), txt, font=f, fill=(255, 255, 255, 255))
    # small accent dot (cosmos blue) bottom-right inside the ring
    d.ellipse([S - 40, S - 40, S - 22, S - 22], fill=(56, 189, 248, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    print("watermark ->", path, f"{S}x{S}")


def apply_branding(banner, watermark):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="brandingSettings,id", mine=True).execute()["items"][0]
    ch_id = ch["id"]
    branding = ch.get("brandingSettings", {})
    chan = dict(branding.get("channel", {}))

    # 1) banner upload
    b = yt.channelBanners().insert(media_body=MediaFileUpload(str(banner))).execute()
    branding["image"] = dict(branding.get("image", {}))
    branding["image"]["bannerExternalUrl"] = b["url"]
    print("banner uploaded:", b["url"][:90])

    # 2) title / description / keywords
    chan["title"] = TITLE
    chan["description"] = DESCRIPTION
    chan["keywords"] = KEYWORDS
    branding["channel"] = chan

    yt.channels().update(part="brandingSettings",
                         body={"id": ch_id, "brandingSettings": branding}).execute()
    print("channel title/description/keywords updated")

    # 3) watermark
    yt.watermarks().set(channelId=ch_id,
                        media_body=MediaFileUpload(str(watermark))).execute()
    print("watermark set")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    banner = ASSETS / "banner.png"
    wm = ASSETS / "watermark.png"
    make_banner(banner)
    make_watermark(wm)
    if a.apply:
        apply_branding(banner, wm)


if __name__ == "__main__":
    main()
