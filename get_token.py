#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-time LOCAL helper: creates token.json (OAuth desktop flow) for uploading.
Run:  python get_token.py
It opens your browser -> sign in with the SAME Google account that owns the YouTube channel
-> click Allow -> token.json is written next to this script.
"""
import json
import urllib.request, urllib.parse, webbrowser
from pathlib import Path

# NOTE: Google does NOT allow mixing YouTube scopes with Drive scopes in one consent
# request. This token is YouTube-only (upload + manage). For Drive backup create a
# separate token with get_token_drive.py (optional).
SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
])

def main():
    src = Path("client_secret.json")
    if not src.exists():
        alt = Path("client_secret_web.json")
        if alt.exists():
            src = alt
        else:
            ids = list(Path(".").glob("client_secret*.json"))
            if ids:
                src = ids[0]
            else:
                raise SystemExit("client_secret.json not found - download it from Google Cloud Console > Credentials > your OAuth Client ID (Desktop app)")
    data = json.loads(src.read_text())
    conf = data.get("installed") or data.get("web") or {}
    client_id = conf["client_id"]
    client_secret = conf["client_secret"]

    params = {
        "client_id": client_id,
        "redirect_uri": "http://localhost:8765/",
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    import http.server, threading

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    print("AUTH_URL:", auth_url, flush=True)

    code_holder = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path).query
            code = urllib.parse.parse_qs(q).get("code", [None])[0]
            code_holder["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Token received! You can close this tab.</h1>")
        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("localhost", 8765), Handler)
    server.handle_request()
    code = code_holder.get("code")
    if not code:
        raise SystemExit("No authorization code received.")

    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "http://localhost:8765/",
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        tok = json.loads(r.read())

    out = {
        "token": tok["access_token"],
        "refresh_token": tok.get("refresh_token") or "",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES.split(),
        "expiry": "2099-01-01T00:00:00Z",
    }
    Path("token.json").write_text(json.dumps(out, indent=2))
    print("OK - token.json created. Keep it SECRET (it lets anyone upload to your channel).")

if __name__ == "__main__":
    main()
