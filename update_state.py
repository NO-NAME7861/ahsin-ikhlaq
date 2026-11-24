#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atomically advance state/episodes.json on the remote branch.

Reads the locally-completed episode list ONCE (before any git checkout), then
unions it with the remote state, computes the next id from episodes.csv, and
commits+pushes with retries.

Important: the local "done" set is captured up-front. An earlier version
re-read the local file inside the retry loop, but the loop had already
overwritten it with `git checkout origin/main -- state/episodes.json`, so a
rejected push made the retry think there was nothing to record (the state
then silently froze).
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
local = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"next_id": ids[0], "done": []}
local_done = set(local.get("done", []))  # captured before any checkout

if not local_done:
    print("local state has no completed ids; nothing to record")
    sys.exit(0)

for attempt in range(5):
    run(["git", "fetch", "origin", "main"], check=True)
    remote = load_from_ref("origin/main") or {"next_id": ids[0], "done": []}
    remote_done = set(remote.get("done", []))

    pending = [i for i in ids if i in local_done and i not in remote_done]
    if not pending:
        print("no new done ids to record; remote already ahead, nothing to do")
        print(f"remote state: {remote}")
        break

    # keep canonical csv order so the file stays diff-friendly
    done = [i for i in ids if i in remote_done or i in pending]
    cur_idx = max(ids.index(i) for i in pending)
    next_id = ids[(cur_idx + 1) % len(ids)]
    new_state = {"next_id": next_id, "done": done}

    run(["git", "checkout", "origin/main", "--", "state/episodes.json"])
    STATE.write_text(json.dumps(new_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run(["git", "add", "state/episodes.json"])
    # The quality history is what makes "every video beats the last one" work,
    # so it must be committed with the episode state (otherwise each CI run
    # starts from an empty ladder).
    qfile = ROOT / "state" / "quality.json"
    if qfile.exists():
        run(["git", "add", "state/quality.json"])
    p = run(["git", "commit", "-m", "chore: advance episode state + quality history"], check=False)
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
    sys.exit("could not push state after 5 attempts")
