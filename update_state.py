#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atomically advance state/episodes.json on the remote branch.
Reads remote state from origin/main, adds the locally-completed episode,
computes the next id from episodes.csv, then commits+pushes with retries.
"""
import os, sys, json, csv, time, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "episodes.json"
CSV_NAME = os.environ.get("EPISODES_CSV", "episodes.csv")
CSVF = ROOT / CSV_NAME

def run(cmd, check=True):
    return subprocess.run(cmd, cwd=str(ROOT), check=check,
                          capture_output=True, text=True)

def load_ids():
    return [r["id"] for r in csv.DictReader(open(CSVF, encoding="utf-8"))]

def load_from_ref(ref):
    p = run(["git", "show", f"{ref}:state/episodes.json"], check=False)
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)

ids = load_ids()

for attempt in range(3):
    run(["git", "fetch", "origin", "main"], check=True)
    remote = load_from_ref("origin/main") or {"next_id": ids[0], "done": []}
    local = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"next_id": ids[0], "done": []}

    new_ids = [i for i in ids
               if i in local.get("done", []) and i not in remote.get("done", [])]

    if not new_ids:
        print("no new done ids to record; remote already ahead, nothing to do")
        print(f"remote state: {remote}")
        break

    done = list(remote.get("done", [])) + [i for i in new_ids if i not in remote.get("done", [])]
    cur_idx = max(ids.index(i) for i in new_ids)
    next_id = ids[(cur_idx + 1) % len(ids)]
    new_state = {"next_id": next_id, "done": done}

    run(["git", "checkout", "origin/main", "--", "state/episodes.json"])
    STATE.write_text(json.dumps(new_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run(["git", "add", "state/episodes.json"])
    p = run(["git", "commit", "-m", "chore: advance episode state"], check=False)
    if p.returncode != 0:
        print("nothing to commit; state already in sync")
        break
    try:
        run(["git", "push", "origin", "HEAD:main"])
        print("state pushed:", json.dumps(new_state, ensure_ascii=False))
        break
    except subprocess.CalledProcessError:
        print(f"push rejected (attempt {attempt + 1}); re-fetching and retrying")
        time.sleep(3)
else:
    sys.exit("could not push state after 3 attempts")
