#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail factory for Ahsin Akhlaq.

Takes a base image + a 2-4 word hook + a pillar, and renders a 1280x720
YouTube thumbnail with:
  - cover-cropped, slightly enhanced base image
  - left-side dark gradient so the hook stays readable at feed size
  - huge bold uppercase hook text with thick outline
  - accent bar + pillar badge (COSMOS / MIND / BRAIN) bottom-right,
    which also covers the Pollinations watermark corner
  - small channel wordmark top-left

CLI:
  python thumbnail.py --image base.jpg --hook "WHERE IS EVERYONE?" \
      --pillar cosmos --out thumb.jpg
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1280, 720

PILLARS = {
    "cosmos": {"label": "COSMOS", "accent": (56, 189, 248)},
    "mind":   {"label": "MIND",   "accent": (167, 139, 250)},
    "brain":  {"label": "BRAIN",  "accent": (251, 146, 60)},
}

# Keyword routing for the three pillars. Scoring is word-boundary based;
# multi-word phrases count for more than single words, so "hard problem"
# beats "universe" but "black hole" beats "memory".
_MIND_WORDS = (
    "consciousness", "conscious", "mind", "qualia", "hard problem",
    "split-brain", "split brain", "anesthesia", "near-death", "near death",
    "phantom limb", "predictive processing", "perception", "perceived",
    "free will", "libet", "binding problem", "metzinger", "chalmers", "seth",
    "sentience", "awareness", "self", "ego", "identity", "who are you",
    "hallucinat", "subjective", "overview effect", "reality",
)
_BRAIN_WORDS = (
    "psychology", "psychological", "cognitive", "cognition", "bias", "biases",
    "dissonance", "habit", "habits", "procrastinat", "loneliness", "conformity",
    "awe", "attention", "motivation", "emotion", "emotional", "anxiety", "fear",
    "stress", "trauma", "relationship", "attachment", "willpower", "decision",
    "decisions", "behavior", "behaviour", "spotlight effect", "bystander",
    "dunning", "placebo", "loss aversion", "peak-end", "kahneman", "tversky",
    "smart people", "dumb choices", "moral", "good or evil", "brain", "memory",
    "memories", "learning", "reward", "dopamine", "addiction", "misinformation",
    "perceived time", "time perception",
)
_COSMOS_WORDS = (
    "universe", "cosmos", "cosmic", "galaxy", "galaxies", "black hole", "star",
    "stars", "planet", "planets", "space", "big bang", "inflation", "quantum",
    "entropy", "dark matter", "dark energy", "fermi", "drake", "multiverse",
    "simulation", "time dilation", "relativity", "nebula", "telescope", "jwst",
    "voyager", "europa", "mars", "moon", "sun", "light-year", "redshift",
    "physics", "gravity", "hawking", "einstein", "bostrom", "kardashev", "dyson",
    "pale blue dot", "exoplanet", "asteroid", "comet", "supernova", "neutron",
    "pulsar", "quasar", "cosmology", "observable universe",
)

_PILLAR_RE = {
    "mind": re.compile(r"\b(" + "|".join(_MIND_WORDS) + r")\b", re.I),
    "brain": re.compile(r"\b(" + "|".join(_BRAIN_WORDS) + r")\b", re.I),
    "cosmos": re.compile(r"\b(" + "|".join(_COSMOS_WORDS) + r")\b", re.I),
}


def pillar_for(text: str) -> str:
    """Pick the strongest pillar signal in a topic/title. Defaults to cosmos."""
    t = (text or "").lower()
    scores = {}
    for pillar, rx in _PILLAR_RE.items():
        score = 0
        for m in rx.finditer(t):
            score += len(m.group(0).split())  # multi-word phrases weigh more
        scores[pillar] = score
    best = max(scores, key=lambda k: (scores[k], k == "cosmos"))
    return best if scores[best] > 0 else "cosmos"


def _font_path() -> str:
    """Return a heavy sans font that exists on this machine."""
    candidates = [
        "C:/Windows/Fonts/ariblk.ttf",   # Arial Black (Windows)
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Ubuntu CI
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return ""


_FONT_CACHE = {}


def _font(size: int):
    if size not in _FONT_CACHE:
        path = _font_path()
        _FONT_CACHE[size] = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    return _FONT_CACHE[size]


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale + center-crop to exactly w x h."""
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    nw, nh = int(src_w * scale + 0.5), int(src_h * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _wrap(draw, text: str, font, max_width: int):
    """Greedy word wrap. Never drops words. Returns (lines, widest_line_width)."""
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    widest = max((draw.textlength(l, font=font) for l in lines), default=0)
    return lines, widest


def _fit_hook(draw, hook: str, max_width: int, max_height: int):
    """Find the largest font size that fits the whole hook in the box."""
    hook = hook.upper().strip()
    for size in range(150, 45, -4):
        font = _font(size)
        lines, widest = _wrap(draw, hook, font, max_width)
        line_h = int(size * 1.08)
        total_h = line_h * len(lines)
        if widest <= max_width and total_h <= max_height and len(lines) <= 4:
            return font, lines, line_h, size
    font = _font(46)
    lines, _ = _wrap(draw, hook, font, max_width)
    return font, lines, int(46 * 1.08), 46


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_thumbnail(base_image, hook: str, pillar: str, out_path,
                   channel: str = "AHSIN AKHLAQ",
                   trim_bottom: float = 0.08, trim_right: float = 0.05) -> Path:
    """Render a branded 1280x720 thumbnail. Returns the output path.

    trim_bottom/trim_right: fractions cut from the source before cover-cropping.
    Video-frame fallbacks carry burned-in subtitles, so they need a bigger cut.
    """
    pillar = pillar if pillar in PILLARS else pillar_for(hook)
    accent = PILLARS[pillar]["accent"]
    label = PILLARS[pillar]["label"]

    img = Image.open(base_image).convert("RGB")
    # Generators often stamp a logo bottom-right, and video-frame fallbacks can
    # carry burned-in subtitles along the bottom. Trim those edges, then
    # cover-crop back to exactly 16:9.
    sw, sh = img.size
    img = img.crop((0, 0, int(sw * (1 - trim_right)), int(sh * (1 - trim_bottom))))
    img = _cover(img, W, H)
    # Punch up the photo a little; thumbnails are viewed small.
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.18)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))

    # Left-side gradient (dark -> transparent) for text contrast.
    grad = Image.new("L", (W, 1), 0)
    for x in range(W):
        a = 0 if x >= 820 else int(235 * ((820 - x) / 820) ** 0.85)
        grad.putpixel((x, 0), a)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, grad.resize((W, H)))

    # Subtle bottom gradient so the badge/wordmark sit on something.
    bgrad = Image.new("L", (1, H), 0)
    for y in range(H):
        bgrad.putpixel((0, y), int(170 * max(0, (y - H * 0.62) / (H * 0.38)) ** 1.4))
    img = Image.composite(black, img, bgrad.resize((W, H)))

    draw = ImageDraw.Draw(img)

    # --- hook text -------------------------------------------------------
    box_x, box_y = 56, 92
    max_w, max_h = 700, 430
    font, lines, line_h, size = _fit_hook(draw, hook, max_w, max_h)

    stroke = max(6, size // 11)
    y = box_y
    text_top = y
    for line in lines:
        draw.text((box_x, y), line, font=font, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += line_h
    text_bottom = y

    # accent bar to the left of the hook
    draw.rounded_rectangle([box_x - 26, text_top + 6, box_x - 12, text_bottom - 10],
                           radius=7, fill=accent)

    # --- channel wordmark (top-left) -------------------------------------
    wm_font = _font(26)
    draw.text((box_x, 38), channel, font=wm_font, fill=(255, 255, 255),
              stroke_width=3, stroke_fill=(0, 0, 0))
    draw.ellipse([box_x - 26, 46, box_x - 14, 58], fill=accent)

    # --- pillar badge (bottom-right, covers the generator watermark) ------
    bf = _font(30)
    tw = draw.textlength(label, font=bf)
    pad_x, bh = 26, 58
    bw = int(tw + pad_x * 2)
    bx2, by2 = W - 34, H - 34
    bx1, by1 = bx2 - bw, by2 - bh
    _rounded(draw, [bx1, by1, bx2, by2], radius=12, fill=accent)
    draw.text((bx1 + pad_x, by1 + (bh - 36) // 2 - 2), label, font=bf, fill=(8, 10, 16))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92, optimize=True, progressive=True)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--hook", required=True)
    ap.add_argument("--pillar", default="auto", choices=["auto", "cosmos", "mind", "brain"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pillar = pillar_for(a.hook) if a.pillar == "auto" else a.pillar
    p = make_thumbnail(a.image, a.hook, pillar, a.out)
    print("wrote", p)


if __name__ == "__main__":
    main()
