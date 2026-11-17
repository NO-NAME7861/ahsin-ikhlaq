#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload GitHub backup bundles/archives to Google Drive using ADC."""
import json, os, sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = Path(r"C:\Users\Park-Edge\Documents\Default Project\github-backup")
FOLDER_NAME = "GitHub_Backup"
FILES = sorted(p for p in BACKUP_DIR.glob("*") if p.is_file())
TOKEN_PATH = Path(os.environ["APPDATA"]) / "gcloud" / "application_default_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    if not BACKUP_DIR.exists() or not FILES:
        sys.exit(f"backup dir missing or empty: {BACKUP_DIR}")
    if not TOKEN_PATH.exists():
        sys.exit(f"ADC credentials missing at {TOKEN_PATH}")
    print("files to upload:", [f.name for f in FILES])

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    # find or create folder
    q = f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = drive.files().list(q=q, spaces="drive", fields="files(id,name)").execute()
    if res.get("files"):
        fid = res["files"][0]["id"]
        print("reusing existing folder:", FOLDER_NAME, fid)
    else:
        meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
        fid = drive.files().create(body=meta, fields="id").execute()["id"]
        print("created folder:", FOLDER_NAME, fid)

    for f in FILES:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"- uploading {f.name} ({size_mb:.1f} MB)...")
        # check if file with same name exists in folder
        eq = f"'{fid}' in parents and name = '{f.name}' and trashed = false"
        existing = drive.files().list(q=eq, spaces="drive", fields="files(id,name)").execute().get("files", [])
        media = MediaFileUpload(str(f), resumable=True)
        if existing:
            res = drive.files().update(fileId=existing[0]["id"], media_body=media,
                                       fields="id,name,size").execute()
            print(f"  overwritten in Drive: id={res['id']}  size={res.get('size')}")
        else:
            meta = {"name": f.name, "parents": [fid]}
            res = drive.files().create(body=meta, media_body=media,
                                       fields="id,name,size").execute()
            print(f"  uploaded to Drive: id={res['id']}  size={res.get('size')}")

    print("\nFolder: https://drive.google.com/drive/folders/" + fid)

if __name__ == "__main__":
    main()
