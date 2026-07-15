#!/usr/bin/env python3
"""
MAL → AniList Sync Bot
Reads your full anime + manga list from MAL and syncs to AniList.

Logic:
  - MAL entry found in AniList DB + not on your AniList list → Add it
  - MAL entry not found in AniList DB at all                 → Skip
  - AniList entry not in MAL                                 → Skip
  - Both have it, AniList progress >= MAL                    → Skip
  - Both have it, AniList progress < MAL                     → Update
  - Same progress                                            → Skip

Runs via GitHub Actions on a schedule (see sync_interval_days in config.json).

All credentials come from config.json in this same directory. See README.md
for how to fill it in (hand-edit it, or run the "Setup - Config" workflow).
"""

import json
import os
import sys
import time
import requests
from datetime import datetime

BASE       = os.path.dirname(os.path.abspath(__file__))
CONFIG_F   = os.path.join(BASE, "config.json")
LOG_F      = os.path.join(BASE, "anilist_sync_log.txt")
MAL_TOK    = os.path.join(BASE, "mal_token.json")
AL_TOK     = os.path.join(BASE, "anilist_token.json")
LAST_RUN   = os.path.join(BASE, "anilist_last_run.txt")

REQUIRED_STRING_FIELDS = [
    "mal_client_id",
    "anilist_client_id",
    "anilist_client_secret",
    "mal_username",
]


# ── CONFIG LOADING + VALIDATION ───────────────
def load_config():
    """
    Load config.json and validate it. Fails loudly with a clear, actionable
    message (no stack trace) if anything required is missing — this is the
    only "support channel" most users of this template will ever see.
    """
    if not os.path.exists(CONFIG_F):
        print(
            "ERROR: config.json not found.\n\n"
            "This repo needs a config.json in its root directory with your\n"
            "MAL and AniList credentials. See the README's 'Setup' section:\n"
            "  1) Hand-edit config.json directly (in the GitHub web UI or locally), OR\n"
            "  2) Run the 'Setup - Config' workflow from the Actions tab.\n"
        )
        sys.exit(1)

    try:
        with open(CONFIG_F, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"ERROR: config.json exists but could not be read/parsed ({e}).\n"
            "Make sure it's valid JSON. See the README's 'Setup' section for the\n"
            "expected format, or re-run the 'Setup - Config' workflow to regenerate it.\n"
        )
        sys.exit(1)

    missing = [
        field for field in REQUIRED_STRING_FIELDS
        if not str(config.get(field, "")).strip()
    ]
    if missing:
        print(
            "ERROR: config.json is missing required values: "
            + ", ".join(missing) + "\n\n"
            "Fill these in before the sync can run. You can either:\n"
            "  1) Hand-edit config.json directly (in the GitHub web UI or locally), OR\n"
            "  2) Run the 'Setup - Config' workflow from the Actions tab to fill\n"
            "     them in via a form.\n\n"
            "See the README's 'Setup' section for where to get MAL/AniList\n"
            "client IDs and secrets (you must register your own OAuth apps).\n"
        )
        sys.exit(1)

    # sync_interval_days is optional-with-default, not part of the hard requirement
    if "sync_interval_days" not in config:
        config["sync_interval_days"] = 23

    return config


CONFIG                = load_config()
MAL_CLIENT_ID          = CONFIG["mal_client_id"]
ANILIST_CLIENT_ID      = CONFIG["anilist_client_id"]
ANILIST_CLIENT_SECRET  = CONFIG["anilist_client_secret"]
MAL_USERNAME           = CONFIG["mal_username"]
SYNC_INTERVAL_DAYS     = CONFIG["sync_interval_days"]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_F, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── INTERVAL CHECK (days-based, not calendar month) ───
def days_since_last_run():
    if not os.path.exists(LAST_RUN):
        return None
    with open(LAST_RUN) as f:
        content = f.read().strip()
    try:
        last = datetime.strptime(content, "%Y-%m-%d")
    except ValueError:
        return None
    return (datetime.now() - last).days

def already_ran_recently():
    days = days_since_last_run()
    if days is None:
        return False
    return days < SYNC_INTERVAL_DAYS

def mark_ran_today():
    with open(LAST_RUN, "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d"))

# ── MAL STATUS → ANILIST STATUS ───────────────
MAL_TO_AL_STATUS = {
    "watching":      "CURRENT",
    "reading":       "CURRENT",
    "completed":     "COMPLETED",
    "on_hold":       "PAUSED",
    "dropped":       "DROPPED",
    "plan_to_watch": "PLANNING",
    "plan_to_read":  "PLANNING",
}

# ── MAL TOKEN ─────────────────────────────────
def get_mal_token():
    if not os.path.exists(MAL_TOK):
        log("ERROR: mal_token.json not found. Run the setup_mal workflow first.")
        return None
    with open(MAL_TOK) as f:
        td = json.load(f)
    if td.get("expires_at", 0) > time.time() + 120:
        return td["access_token"]
    log("Refreshing MAL token...")
    r = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id":     MAL_CLIENT_ID,
            "grant_type":    "refresh_token",
            "refresh_token": td["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if r.status_code != 200:
        log(f"MAL token refresh failed: {r.status_code}")
        return None
    td = r.json()
    td["expires_at"] = time.time() + td.get("expires_in", 3600)
    with open(MAL_TOK, "w") as f:
        json.dump(td, f)
    log("MAL token refreshed OK.")
    return td["access_token"]

# ── ANILIST TOKEN ─────────────────────────────
def get_anilist_token():
    if not os.path.exists(AL_TOK):
        log("ERROR: anilist_token.json not found. Run the setup_anilist workflow first.")
        return None
    with open(AL_TOK) as f:
        td = json.load(f)
    return td.get("access_token")

# ── ANILIST REQUEST WITH RETRY ────────────────
def anilist_request(payload, al_token, retries=3):
    """POST to AniList GraphQL with retry + backoff on connection errors."""
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://graphql.anilist.co",
                json=payload,
                headers={
                    "Authorization": f"Bearer {al_token}",
                    "Content-Type":  "application/json",
                    "Accept":        "application/json",
                },
                timeout=15,
            )
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                log(f"  Rate limited — waiting {wait}s...")
                time.sleep(wait)
                continue
            return r
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 10
                log(f"  Connection error — retrying in {wait}s... ({e})")
                time.sleep(wait)
            else:
                log(f"  Failed after {retries} attempts — skipping")
                return None
    return None

# ── FETCH MAL LIST ─────────────────────────────
def fetch_mal_list(media_type, token):
    entries = []
    offset  = 0
    fields  = "list_status{status,score,num_episodes_watched,num_chapters_read}"

    while True:
        r = requests.get(
            f"https://api.myanimelist.net/v2/users/@me/{media_type}list",
            params={"fields": fields, "limit": 1000, "offset": offset},
            headers={
                "Authorization":   f"Bearer {token}",
                "X-MAL-CLIENT-ID": MAL_CLIENT_ID,
            },
            timeout=15,
        )
        if r.status_code != 200:
            log(f"MAL {media_type} list fetch failed: {r.status_code}")
            break

        data  = r.json()
        nodes = data.get("data", [])
        for node in nodes:
            n  = node["node"]
            ls = node.get("list_status", {})
            progress = (
                ls.get("num_episodes_watched", 0)
                if media_type == "anime"
                else ls.get("num_chapters_read", 0)
            )
            entries.append({
                "mal_id":   n["id"],
                "title":    n.get("title", ""),
                "status":   ls.get("status", ""),
                "score":    ls.get("score", 0),
                "progress": progress,
                "type":     media_type,
            })

        if not data.get("paging", {}).get("next"):
            break
        offset += 1000
        time.sleep(1)

    return entries

# ── ANILIST: GET ENTRY BY MAL ID ──────────────
def get_anilist_entry(mal_id, media_type, al_token):
    al_type = "ANIME" if media_type == "anime" else "MANGA"
    query = """
    query ($malId: Int, $type: MediaType) {
      Media(idMal: $malId, type: $type) {
        id
        mediaListEntry {
          status
          progress
          score(format: POINT_10)
        }
      }
    }
    """
    r = anilist_request(
        {"query": query, "variables": {"malId": mal_id, "type": al_type}},
        al_token,
    )
    if r is None or r.status_code != 200:
        return None

    data  = r.json()
    media = data.get("data", {}).get("Media")
    if not media:
        return None  # not in AniList DB

    al_id = media["id"]
    entry = media.get("mediaListEntry")

    if entry:
        return al_id, entry.get("status"), entry.get("progress", 0), entry.get("score", 0)
    else:
        return al_id, None, 0, 0  # in DB, not on user list

# ── ANILIST: UPDATE / ADD ENTRY ─────
def update_anilist_entry(al_id, status, progress, score, al_token):
    mutation = """
    mutation ($mediaId: Int, $status: MediaListStatus, $progress: Int, $score: Float) {
      SaveMediaListEntry(mediaId: $mediaId, status: $status, progress: $progress, score: $score) {
        id
        status
        progress
        score
      }
    }
    """
    r = anilist_request(
        {
            "query": mutation,
            "variables": {
                "mediaId":  al_id,
                "status":   status,
                "progress": progress,
                "score":    float(score),
            },
        },
        al_token,
    )
    if r is None:
        return False
    return r.status_code == 200

# ── MAIN ────────────────────────────────────────────────
def sync():
    days = days_since_last_run()
    if already_ran_recently():
        log(f"Last sync was {days} day(s) ago — interval is {SYNC_INTERVAL_DAYS} days. Skipping.")
        return

    log("=" * 48)
    log("MAL → AniList sync started")
    if days is not None:
        log(f"({days} days since last run, interval={SYNC_INTERVAL_DAYS})")

    if not MAL_USERNAME:
        log("ERROR: mal_username is empty. Fill it in config.json"); return

    mal_token = get_mal_token()
    if not mal_token:
        return

    al_token = get_anilist_token()
    if not al_token:
        return

    total_updated = 0
    total_added   = 0
    total_skipped = 0

    for media_type in ["anime", "manga"]:
        log(f"--- {media_type.upper()} ---")
        mal_list = fetch_mal_list(media_type, mal_token)
        log(f"Fetched {len(mal_list)} {media_type} entries from MAL.")

        for entry in mal_list:
            mal_id    = entry["mal_id"]
            title     = entry["title"]
            status    = entry["status"]
            score     = entry["score"]
            progress  = entry["progress"]
            al_status = MAL_TO_AL_STATUS.get(status, "CURRENT")

            result = get_anilist_entry(mal_id, media_type, al_token)
            time.sleep(1)  # stay well within AniList rate limit

            if result is None:
                log(f"  SKIP (not in AniList DB): {title}")
                total_skipped += 1
                continue

            al_id, my_al_status, my_al_progress, my_al_score = result

            if my_al_status is None:
                # Not on user's AniList → Add
                ok = update_anilist_entry(al_id, al_status, progress, score, al_token)
                if ok:
                    log(f"  ADDED: {title} — {al_status}, progress {progress}, score {score}")
                    total_added += 1
                else:
                    log(f"  FAILED to add: {title}")
                    total_skipped += 1

            elif my_al_progress < progress:
                # AniList behind MAL → Update
                ok = update_anilist_entry(al_id, al_status, progress, score, al_token)
                if ok:
                    log(f"  UPDATED: {title} — {my_al_progress}→{progress}, score {my_al_score}→{score}")
                    total_updated += 1
                else:
                    log(f"  FAILED to update: {title}")
                    total_skipped += 1

            else:
                log(f"  OK: {title}")

            time.sleep(1)

    mark_ran_today()
    log(f"Done — Added: {total_added} | Updated: {total_updated} | Skipped: {total_skipped}")
    log("=" * 48)

if __name__ == "__main__":
    sync()
