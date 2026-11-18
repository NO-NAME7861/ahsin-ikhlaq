# Ahsin Akhlaq — Universe & Philosophy YouTube Automation

> ⚠ **Proprietary automation — all rights reserved** (see [LICENSE](LICENSE)).
> Do not copy, redistribute, fork, or adapt this code into your own uploads without the channel owner's
> explicit written permission. The owner's Google credentials and API keys are never committed.

**Channel:** https://www.youtube.com/@ahsin-ikhlaq — deep-dives on the cosmos and the human condition:
cosmology, space exploration, quantum mechanics, philosophy, ethics, and what the universe says about us.

## What this project is

A fully automated YouTube pipeline:

```
LLM (OpenRouter) -> image generation (NASA image library with artwork fallback)
  -> edge-tts voice -> Ken Burns video with subtitles (ffmpeg)
  -> YouTube upload (YouTube Data API v3) -> playlist + Drive backup
```

Runs on GitHub Actions: **3 long-form videos/day, 3 Shorts/day, daily quizzes.**
All content is factual, sourced (NASA, ESA, peer-reviewed journals), and written in Hindi with
English technical terms. No AI boilerplate, no fake facts.

See `episodes.csv` for the 30-episode arc and `promotion_kit.md` for the channel's outreach plan.

## Public here

- The automation pipeline source code
- The episode roadmap (`episodes.csv`)
- The privacy policy and terms of service (`PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`)

## Not included (and never included)

- No Google credentials, client secrets, or refresh tokens — those live in GitHub Secrets only
- No private contact information

Questions about the channel: via the [channel's About page](https://www.youtube.com/@ahsin-ikhlaq/about)
