#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
First-subscriber thank-you video.

A one-off, personal letter to the channel's first subscriber. Reuses the main
pipeline (NASA images -> Neerja voice -> 1080p video -> branded thumbnail ->
YouTube upload) but with a hand-written narration so the tone stays warm and
personal instead of deep-dive.

Run:  python make_thankyou.py           # build + upload (public)
      DRY_RUN=1 python make_thankyou.py # build only
"""
import os
import sys
from pathlib import Path

# These must be set before importing the pipeline module (it reads env at import).
os.environ.setdefault("N_IMAGES", "12")
os.environ.setdefault("PRIVACY_STATUS", "public")
os.environ.setdefault("UPLOAD", "1")

import generate_episode as ge  # noqa: E402

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work_thankyou"
WORK.mkdir(exist_ok=True)
ge.WORK = WORK  # keep this video's artifacts separate from the daily rotation

TITLE = "Thank You, Our First Subscriber - This Video Is For You"

DESCRIPTION = (
    "This video is a personal thank-you to the first person who ever subscribed to "
    "Ahsin Akhlaq - the one who believed in a channel about the universe and the mind "
    "before anyone else did.\n\n"
    "Every civilisation begins with one person who says yes. This is a short letter about "
    "being first: Fermi's question in 1950, Voyager's Golden Record in 1977, Carl Sagan's "
    "line that we are a way for the cosmos to know itself, and the overview effect that "
    "changes astronauts who see Earth from orbit.\n\n"
    "Sources: NASA, ESA, peer-reviewed journals.\n\n"
    "Subscribe to follow the journey - COSMOS, MIND and BRAIN, every single day."
)

TAGS = [
    "first subscriber", "thank you", "gratitude", "ahsin akhlaq", "universe",
    "cosmos", "philosophy", "space channel", "being first", "carl sagan",
    "voyager golden record", "overview effect", "subscriber thank you",
]

NARRATION = """Dosto, aaj ka episode thora mukhtalif hai. Aaj hum kisi galaxy ki baat nahi karenge, kisi black hole ki nahi. Aaj hum us ek insaan ki baat karenge jisne hamare channel par bharosa kiya.

Aap ne subscribe ka button dabaya. Ye ek chhota sa click tha. Lekin us click ke peeche ek bara faisla tha. Aap ne kisi cheez par yaqeen kiya jab us ke paas abhi koi proof nahi tha. Sirf ek naya channel, kuch videos, aur ek umeed.

Science mein aise logon ko first mover kehte hain. 1950 mein Enrico Fermi ne ek sawal poocha: agar brahmand itna bara hai, to sab kahan hain? Us waqt kisi ke paas jawab nahi tha. Lekin us ek sawal ne poori generation ko sochne par majboor kar diya. Ek sawal, jo pehle kisi ne nahi poocha tha.

1977 mein NASA ne Voyager 1 ko space mein bheja. Us ke sath ek golden record gaya. Us record par insani awaz thi, dhoop ki roshni, barish ki awaz, bachon ka hansna. Hum ne apni kahani solar system ki hadd se bahar bhej di, jab humein pata bhi nahi tha ke koi sunega ya nahi. Ye hai yaqeen. Ye hai pehla qadam.

Carl Sagan ne kaha tha: hum brahmand ka wo hissa hain jo khud ko jaanta hai. Aaj aap ne hamare chhote se channel ko dekh kar ye sabit kar diya ke koi bhi cheez akeli nahi hoti. Har bara kaam ek chhote se yaqeen se shuru hota hai.

Astronauts jab Earth ko orbit se dekhte hain to unhe overview effect hota hai. Borders ghayab ho jate hain. Sirf ek chhota sa neela planet reh jata hai. Aaj aap ne humare liye wohi kaam kiya. Aap ne humein akela mehsoos nahi hone diya.

To ye video sirf aap ke liye hai. Aap ka naam humein nahi pata, lekin aap ka yaqeen humein pata hai. Aap wo pehle insaan hain jisne kaha: haan, ye channel kuch ban sakta hai.

Hum promise karte hain: har video pehli video se behtar hogi. Har hafte hum brahmand ke naye raaz, dimagh ke naye sawal, aur insaan ke naye jawab layenge. Hum aap ka waqt zaya nahi karenge.

Agar aap yahan tak aa gaye hain, to ek chhota sa kaam karein. Neeche comment mein likhein ke aap kis sawal ka jawab chahte hain. Ho sakta hai wo sawal hamari agli video ka topic ban jaye.

Shukriya. Dil se shukriya. Aap pehle the. Aur pehla hona sab se mushkil kaam hai.

Kyunke koi bhi civilization pehle insaan ke bina shuru nahi hoti. Aap hamare pehle insaan hain. Ab hum stars tak chalenge, sath mein."""

# (prompt for generated fallback, NASA library search phrase)
SHOTS = [
    ("planet Earth seen from orbit at night, city lights glowing through clouds, cinematic, photorealistic", "earth from orbit"),
    ("the Voyager golden record floating in deep space, gold surface, cinematic, photorealistic", "voyager golden record"),
    ("the pale blue dot - Earth as a tiny speck in a vast dark space photograph, cinematic", "pale blue dot"),
    ("astronaut floating above Earth during a spacewalk, visor reflecting the planet, cinematic", "astronaut spacewalk"),
    ("the Milky Way arching over a dark mountain ridge, long exposure night sky, cinematic", "milky way"),
    ("the Sun rising over Earth's horizon seen from orbit, blue atmosphere glowing, cinematic", "sunrise earth orbit"),
    ("a lone human silhouette standing under an enormous starry sky, cinematic, high contrast", "star field"),
    ("the Orion nebula in vivid colour, deep space telescope photograph, cinematic", "orion nebula"),
    ("a deep field of thousands of distant galaxies, telescope image, cinematic", "hubble deep field"),
    ("Earth rising above the Moon's grey horizon, cinematic, photorealistic", "earthrise"),
    ("a dense star cluster glittering in deep space, cinematic, high contrast", "star cluster"),
    ("Earth's curved horizon and thin blue atmosphere seen from space, cinematic, photorealistic", "earth atmosphere"),
]


def main():
    ge.log("building first-subscriber thank-you video")

    (WORK / "narration.txt").write_text(NARRATION, encoding="utf-8")
    ge.log(f"narration words: {len(NARRATION.split())}")

    image_paths = []
    seed0 = 20261124
    for i, (prompt, query) in enumerate(SHOTS):
        dest = WORK / f"img_{i:02d}.png"
        if dest.exists() and dest.stat().st_size > 15_000:
            image_paths.append(dest)
            continue
        if ge.gen_image(prompt + ge.IMAGE_SUFFIX, dest, seed0 + i, query=query):
            image_paths.append(dest)
        ge.time.sleep(2)
    if len(image_paths) < 6:
        sys.exit(f"only {len(image_paths)} images generated - aborting")
    ge.log(f"images ready: {len(image_paths)}")

    mp3, srt = WORK / "narration.mp3", WORK / "narration.srt"
    if not (mp3.exists() and mp3.stat().st_size > 50_000 and srt.exists()):
        ge.run_tts(WORK / "narration.txt", mp3, srt)
    dur = ge.media_duration(mp3)
    ge.log(f"narration duration: {dur:.1f}s ({dur / 60:.2f} min)")

    thumb_base = WORK / "thumb_base_v2.png"
    if not (thumb_base.exists() and thumb_base.stat().st_size > 15_000):
        ge.gen_image("planet Earth fully lit against deep black space, blue marble, "
                     "cinematic, high contrast, photorealistic" + ge.THUMB_SUFFIX,
                     thumb_base, seed0 + 999, query="blue marble earth")

    from thumbnail import make_thumbnail
    thumb = WORK / "thumb_thankyou.jpg"
    make_thumbnail(thumb_base, "YOU WERE FIRST", "mind", thumb)
    ge.log(f"thumbnail built: {thumb}")

    out_mp4 = WORK / "thankyou_first_subscriber.mp4"
    if not (out_mp4.exists() and out_mp4.stat().st_size > 1_000_000):
        ge.build_video(image_paths, mp3, srt, out_mp4, thumb)

    if os.environ.get("DRY_RUN", "0") == "1" or os.environ.get("UPLOAD", "1") != "1":
        ge.log("build only - video at:", out_mp4)
        return

    ep = {
        "title": TITLE,
        "description": DESCRIPTION,
        "tags": TAGS,
        "thumbnail_hook": "YOU WERE FIRST",
    }
    vid = ge.youtube_upload(ep, out_mp4, thumb)
    ge.add_to_playlist(vid)
    try:
        ge.drive_backup(out_mp4)
    except Exception as e:
        ge.log("drive backup failed (non-fatal):", e)
    ge.log("done -> https://youtu.be/" + vid)


if __name__ == "__main__":
    main()
