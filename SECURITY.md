# Security Policy — Ahsin Akhlaq channel automation

## Scope

This repository contains the automation pipeline for the **Ahsin Akhlaq** YouTube channel.
It is shared publicly for portfolio/transparency reasons. All sensitive credentials
(OAuth tokens, API keys) are held in GitHub Secrets and are never committed. History has
been scrubbed as well.

## Reporting a vulnerability

**Do NOT open a public issue.** Issues are disabled.

Please report vulnerabilities privately using **GitHub Private Vulnerability Reporting**:

https://github.com/NO-NAME7861/universe-explorer/security/advisories/new

We will acknowledge receipt within 72 hours and work with you on a fix before any disclosure.

## What we care about

- OAuth tokens, API keys, or cookies accidentally committed to the repo
- The pipeline writing data outside its intended scope (Google Drive/YouTube)
- Disclosure of personal contact details of the channel owner

## Out of scope

- The YouTube channel content itself (videos, descriptions, tags) — content reports go
  through [YouTube's reporting flow](https://support.google.com/youtube).
- The fact that the automation is public; the source being visible is intentional.
