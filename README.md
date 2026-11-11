# Ahsin Akhlaq — Universe & Philosophy YouTube Automation

Naya channel: **Universe Explorer + Philosophy** — expert-level Hinglish deep-dives (Devanagari Hindi with English technical terms).

```
LLM (OpenRouter free) → photorealistic images (Pollinations, free)
→ edge-tts hi-IN-SwaraNeural voice (free) → subtitles + Ken Burns video (ffmpeg)
→ YouTube upload (YouTube Data API v3) → Google Drive backup
```

Cost: **$0/month** (GitHub Actions free tier). Koi video editing nahi — fully automatic. 1 episode/day default (naye channel ke liye safe — 6/day AI mass-content = monetization/reject risk).

> ⚠️ **Yeh (redacted)/(redacted) wale Google account se ALAG hai.** Naye channel ke liye ALAG Google account use hoga, aur `token.json` / `client_secret.json` is folder mein kabhi copy KARNA hi NAHI.

---

## Pehle ek baar yeh setup karein (~20 minutes)

### STEP 0 — Alag Google account ready karein

1. Naya Gmail account (ya jo account naye channel ke liye dedicated hai) — sign in rakhein
2. [youtube.com](https://www.youtube.com) → profile icon → **Create a channel** → naam: **Ahsin Akhlaq**
3. Channel ban gaya hai ✅ — **https://www.youtube.com/@ahsin-ikhlaq** (naam: Ahsin-Akhlaq).

### STEP 1 — Google Cloud project (NAYE account par)

1. [console.cloud.google.com](https://console.cloud.google.com) — **naye** Google account se sign in karein (browser ka correct profile select karein!)
2. Top bar → **Select project** → **New Project** → naam: `UniverseExplorer` → Create

### STEP 2 — APIs enable karein

1. **APIs & Services** → **Library**
2. **YouTube Data API v3** → Enable
3. **Google Drive API** → Enable

### STEP 3 — OAuth consent screen

1. **OAuth consent screen** → User Type: **External** → Create
2. Fill karein:
   - App name: `UniverseExplorer`
   - User support email: naye account ka email
   - Developer contact: aapka email
3. **Scopes** → Add: `youtube.upload`, `youtube`, `drive.file` → Save & Continue
4. **Test users** → apna naya Gmail add karein → Save
5. ⚠️ **Publish app** (ZAROORI): wapas consent screen page → **"Publish app"** → Confirm.
   (Testing mode mein refresh token **har 7 din** baad expire ho jayega!)

### STEP 4 — OAuth Client ID (Desktop)

1. **Credentials** → **+ Create Credentials** → **OAuth client ID**
2. Application type: **Desktop app** → Name: `universe-uploader` → Create
3. **Download JSON** → rename to **`client_secret.json`**
4. Is folder mein rakh dein: `universe-explorer\client_secret.json`

### STEP 5 — Local token (ek baar, browser mein allow)

**CRITICAL:** Browser ka wo profile use karein jisme **NAYA Google account** signed in hai (ya Incognito window khol kar naye account se login karein) — warna token purane (redacted) account/channel ke liye ban jayega!

```powershell
cd "C:\Users\Park-Edge\Documents\Default Project\universe-explorer"
python -m pip install -r requirements.txt
python get_token.py
```
Browser khulega → **naya** Google account select → Allow → `token.json` ban jayega.

### STEP 6 — GitHub repo + secrets

Repo already banaya jaa chuka hai: **NO-NAME7861/universe-explorer** (private) — wahi GitHub account jaisa purana project.

```powershell
cd "C:\Users\Park-Edge\Documents\Default Project\universe-explorer"
git remote add origin https://github.com/<YOUR-GITHUB>/universe-explorer.git
git push -u origin main

# 1) OpenRouter key — wahi purani key reuse ho sakti hai (OpenRouter account se linked hai, Google account se nahi)
gh secret set OPENROUTER_API_KEY

# 2) token.json ka base64 — NEW account wala token!
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$PWD\token.json")) | gh secret set YOUTUBE_TOKEN_JSON

# 3) (Optional) voice badalni ho to:
gh variable set TTS_VOICE --body "hi-IN-SwaraNeural"
```

### STEP 7 — Pehla run (PRIVATE!)

1. GitHub repo → **Actions** → **Daily Universe Explorer Upload** → **Run workflow**
2. `privacy: private` चुन के Run
3. ~20–60 min baad video Studio mein aayega — watch flow: `work/episode.json` mein generated title/description/narration dikhega (artifact `episode-work` download karke check karein)
4. Sab theek ho to public run karein

Iske baad roz **11:30 PM PKT** (18:30 UTC) khud hota rahega.

---

## Channels ka separation (IMPORTANT)

| Cheez | (redacted) (purana) | Ahsin Akhlaq (naya) |
|---|---|---|
| Google account | Purana | **Alag naya** |
| Folder | `youtube-automation` | `universe-explorer` |
| Repo | `NO-NAME7861/youtube-automation` | naya repo |
| Token | purana `token.json` | **naya token (Step 5)** |
| Playlist | Chinese/Japanese Recaps | `Universe & Philosophy Deep Dives` |

`client_secret.json` / `token.json` kabhi git mein commit na ho — `.gitignore` do tailed hota hai uske liye check karein.

---

## Content quality & honesty guidelines

1. **Fact-check**: LLM kabhi bhi wrong numbers/dates de sakta hai. Description mein source line hai, lekin pehli few uploads ko manually dekhen — koi glaring error ho to `episodes.csv` ka brief refine karein. Galat facts = channel ki credibility khatam.
2. **AI disclosure**: Description already includes *"Yeh video AI-generated visuals aur AI narration se banayi gayi hai"*. YouTube Studio mein pehli upload ke baad **"altered or synthetic content" toggle** manually check/on karein.
3. **"Realistic" images ka matlab**: Pollinations/Flux photorealistic AI renders banata hai — yeh **actual NASA/JWST photos nahi** hote. Description mein yahi likha hai; kabhi bhi claim na karein ki yeh real mission photos hain. (Optional upgrade: NASA images public domain hain — future mein `image_prompts` ki jagah real NASA URLs mixing pipeline mein add kar sakte hain, lekin poori automation complexity badh jayegi.)
4. **Monetization**: Naye channel ko 1,000 subs + 4,000 watch-hours (ya Shorts route) chahiye. AI content ke saath monetization tougher hai — original voice commentary, real insight aur consistency se hi chalega. Koi guaranteed growth nahi — patience.
5. **Uniqueness**: Har brief mein `moral` field philosophical insight hai — yahi woh cheez hai jo generic AI universe channels se different banata hai. Isse weak mat karna.

## Customize

| Cheez | Kaise |
|---|---|
| Voice | `vars.TTS_VOICE`: `hi-IN-SwaraNeural` (Hindi female), `hi-IN-MadhurNeural` (Hindi male), `ur-PK-UzmaNeural` (Urdu), `en-IN-NeerjaNeural` (Indian English) |
| Upload time | `.github/workflows/daily.yml` → cron `30 18 * * *` (UTC) |
| Frequency | Day mein runs badhane hain to cron line add karein — lekin naye channel pe 1/day hi rakhein |
| Episodes | `episodes.csv` — 30 briefs hain; expert-level topics add karein |
| Category | `generate_episode.py` → `categoryId: "27"` (Education) — 24 Entertainment bhi kar sakte hain |
| Images resolution | `W,H` (1024x576), `N_IMAGES` (16) |

## Troubleshooting

| Problem | Solution |
|---|---|
| `token.json missing` | Step 5 dobara — **naye account ke Incognito profile** mein |
| `invalid_grant` | App Testing mode mein hai → Publish app → token dobara |
| Devanagari subtitle boxes (boxes/symbols) | Workflow already `fonts-noto-core` install karti hai; local PC pe Arial Devanagari support karta hai |
| LLM factual error | `episodes.csv` brief mein exact fact likhein (numbers/missions) |
| LLM returns no JSON | `OPENROUTER_MODEL` variable set karein (e.g. `qwen/qwen-2.5-72b-instruct:free`) |
| Upload forbidden | Naye account ka channel verified/active hai? APIs enabled? `youtube.upload` scope consent screen mein? |
| Wrong channel pe upload ho gaya | Token purane account ka bana tha — Step 5 dobara, Incognito mein |

## Files

- `generate_episode.py` — main pipeline (expert Hinglish script, photorealistic images, hi-IN voice)
- `episodes.csv` — 30 expert-level Universe + Philosophy briefs
- `state/episodes.json` — next episode tracker
- `get_token.py` / `get_token_drive.py` — OAuth helpers
- `.github/workflows/daily.yml` — daily 11:30 PM PKT + manual run
