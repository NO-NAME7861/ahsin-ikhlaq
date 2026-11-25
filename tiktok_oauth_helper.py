#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok OAuth helper — guides you through getting an access token.

Steps:
1. Create a TikTok developer app (https://developers.tiktok.com) with "Content Posting" product.
2. Add redirect URI: https://github.com/NO-NAME7861/universe-explorer
3. Copy Client Key and Client Secret.
4. Run this script → it gives you an authorize URL.
5. Open URL in browser, log in, click Authorize.
6. Copy the `code` from the redirect URL and paste it here.
7. Script exchanges code for access_token and prints it.
8. Put that token in GitHub secret: TIKTOK_ACCESS_TOKEN
"""
import os
import sys
import webbrowser
import urllib.parse
import requests

REDIRECT_URI = "https://github.com/NO-NAME7861/universe-explorer"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPE = "video.upload"


def main():
    print("=" * 70)
    print("TikTok OAuth Helper for Ahsin Akhlaq")
    print("=" * 70)
    print()

    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()

    if not client_key or not client_secret:
        print("Client Key / Secret nahi mile environment me.")
        print("Set karein (PowerShell):")
        print('  $env:TIKTOK_CLIENT_KEY="YOUR_CLIENT_KEY"')
        print('  $env:TIKTOK_CLIENT_SECRET="YOUR_CLIENT_SECRET"')
        print()
        client_key = input("Client Key: ").strip()
        client_secret = input("Client Secret: ").strip()
        if not client_key or not client_secret:
            print("Dono chahiye. Exit.")
            return

    # Step 1: Authorize URL
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": "ahsin-akhlaq-oauth",
    }
    authorize_url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("\n--- STEP 1: Authorize ---")
    print("Yeh URL browser me kholein:")
    print(authorize_url)
    print()
    try:
        webbrowser.open(authorize_url)
        print("Browser khol diya gaya.")
    except Exception:
        print("Browser auto nahi khula — manually copy-paste karein.")

    print("\n--- STEP 2: Authorize karein ---")
    print("1. TikTok account se login karein.")
    print("2. 'Authorize' button dabao.")
    print(f"3. Redirect hoga: {REDIRECT_URI}?code=XXXXXX&state=...")
    print("4. URL se `code=` ke baad ka value copy karein.")

    auth_code = input("\nPaste the `code` yahan: ").strip()
    if not auth_code:
        print("Code nahi mila. Exit.")
        return

    # Step 3: Exchange code for access token
    print("\n--- STEP 3: Exchanging code for access token ---")
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
        r.raise_for_status()
        resp = r.json()
        if resp.get("error"):
            print(f"Error: {resp}")
            return
        access_token = resp.get("access_token")
        refresh_token = resp.get("refresh_token")
        expires_in = resp.get("expires_in")
        print("\n" + "=" * 70)
        print("SUCCESS! Access Token mil gaya:")
        print("=" * 70)
        print(f"\nACCESS_TOKEN = {access_token}")
        if refresh_token:
            print(f"REFRESH_TOKEN = {refresh_token}")
        if expires_in:
            print(f"EXPIRES_IN = {expires_in} seconds (~{expires_in // 86400} days)")
        print("\nAb ye token GitHub secret me daal dein:")
        print("  Repository → Settings → Secrets and variables → Actions → New repository secret")
        print("  Name: TIKTOK_ACCESS_TOKEN")
        print(f"  Value: {access_token}")
        print("\nOptional (refresh token bhi daal dein agar chahte hain auto-refresh):")
        print("  Name: TIKTOK_REFRESH_TOKEN")
        print(f"  Value: {refresh_token}")
        print("=" * 70)
    except Exception as e:
        print(f"Token exchange failed: {e}")


if __name__ == "__main__":
    main()