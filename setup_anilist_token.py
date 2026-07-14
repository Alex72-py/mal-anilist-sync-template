#!/usr/bin/env python3
"""
AniList OAuth Token Setup — run ONCE via GitHub Actions workflow_dispatch.

STEP 1 (no input): prints the auth URL to visit.
STEP 2 (after authorizing): re-run with 'anilist_redirect_url' input
        set to the full localhost URL you were redirected to.
"""

import json
import os
import sys
import time
import requests

REDIRECT_URI = "http://localhost"

BASE     = os.path.dirname(os.path.abspath(__file__))
CONFIG_F = os.path.join(BASE, "config.json")
TOK_F    = os.path.join(BASE, "anilist_token.json")

def load_anilist_credentials():
    if not os.path.exists(CONFIG_F):
        print(
            "ERROR: config.json not found.\n"
            "Create it from the template (see README.md) and fill in "
            "anilist_client_id and anilist_client_secret — either by "
            "hand-editing config.json or by running the 'Setup - Config' "
            "workflow first."
        )
        sys.exit(1)

    with open(CONFIG_F) as f:
        try:
            cfg = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: config.json is not valid JSON: {e}")
            sys.exit(1)

    client_id     = cfg.get("anilist_client_id", "")
    client_secret = cfg.get("anilist_client_secret", "")
    missing = [
        name for name, val in
        [("anilist_client_id", client_id), ("anilist_client_secret", client_secret)]
        if not val
    ]
    if missing:
        print(
            "ERROR: config.json is missing values for: " + ", ".join(missing) + "\n"
            "Fill these in either by hand-editing config.json or by running "
            "the 'Setup - Config' workflow first (see README.md)."
        )
        sys.exit(1)

    return client_id, client_secret

ANILIST_CLIENT_ID, ANILIST_CLIENT_SECRET = load_anilist_credentials()

def step1_generate_url():
    auth_url = (
        f"https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
    )
    print("\n" + "=" * 60)
    print("STEP 1 — Open this URL in your browser (any device):")
    print("=" * 60)
    print(f"\n{auth_url}\n")
    print("=" * 60)
    print("Log into AniList if asked, then click Authorize.")
    print("You'll land on a page that won't load (localhost). That's fine.")
    print("Copy the FULL url from the address bar, e.g.:")
    print("  http://localhost/?code=XXXXXXXXXX")
    print("\nThen re-run this workflow with that URL as the")
    print("'anilist_redirect_url' input to complete setup.")
    print("=" * 60 + "\n")

def step2_exchange_code(redirected_url):
    if "code=" not in redirected_url:
        print("ERROR: No code found in the URL you pasted.")
        sys.exit(1)

    code = redirected_url.split("code=")[-1].split("&")[0]

    print("Exchanging code for token...")
    r = requests.post(
        "https://anilist.co/api/v2/oauth/token",
        json={
            "grant_type":    "authorization_code",
            "client_id":     ANILIST_CLIENT_ID,
            "client_secret": ANILIST_CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "code":          code,
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )

    if r.status_code != 200:
        print(f"ERROR: {r.status_code} — {r.text}")
        sys.exit(1)

    td = r.json()
    td["expires_at"] = time.time() + td.get("expires_in", 31536000)

    with open(TOK_F, "w") as f:
        json.dump(td, f)

    print("\n" + "=" * 60)
    print("SUCCESS — anilist_token.json created.")
    print("AniList setup complete. This file will now be committed.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    redirect_url = os.environ.get("ANILIST_REDIRECT_URL", "").strip()
    if redirect_url:
        step2_exchange_code(redirect_url)
    else:
        step1_generate_url()
