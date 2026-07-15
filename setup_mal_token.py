#!/usr/bin/env python3
"""
MAL OAuth Token Setup — run ONCE via GitHub Actions workflow_dispatch.

Two-step process because GitHub Actions can't accept live input mid-run:

STEP 1: Run this workflow with no input. It prints the auth URL in the
    Actions log.

STEP 2 (after you authorize in browser):
    You get redirected to http://localhost/?code=XXXX which won't load.
    Copy that full URL. Re-run this workflow, pasting the URL into the
    'mal_redirect_url' input. This script extracts the code, exchanges
    it for a token, and writes mal_token.json.

Requires config.json (in this same directory) to already have a non-empty
mal_client_id. Fill that in first — either by hand-editing config.json or
by running the "Setup - Config" workflow.
"""

import json
import os
import sys
import time
import requests

BASE      = os.path.dirname(os.path.abspath(__file__))
CONFIG_F  = os.path.join(BASE, "config.json")
TOK_F     = os.path.join(BASE, "mal_token.json")

# Fixed code_verifier (PKCE "plain" method just requires ANY 43-128 char
# string that matches between the auth request and the token exchange).
# Making it a constant means we don't depend on a file surviving between
# two separate GitHub Actions runs.
CODE_VERIFIER = "MalAniListSyncBotFixedVerifierString1234567890ABCDEFGHIJKLMNOPQ"


def load_mal_client_id():
    if not os.path.exists(CONFIG_F):
        print(
            "ERROR: config.json not found.\n\n"
            "Create it first — either hand-edit config.json in the repo, or run\n"
            "the 'Setup - Config' workflow from the Actions tab — before running\n"
            "MAL setup. See the README's 'Setup' section.\n"
        )
        sys.exit(1)

    try:
        with open(CONFIG_F, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: config.json exists but could not be read/parsed ({e}).")
        sys.exit(1)

    client_id = str(config.get("mal_client_id", "")).strip()
    if not client_id:
        print(
            "ERROR: config.json is missing 'mal_client_id'.\n\n"
            "Register your own app at https://myanimelist.net/apiconfig and\n"
            "put its Client ID into config.json (redirect URI must be exactly\n"
            "http://localhost) before running this setup step.\n"
        )
        sys.exit(1)

    return client_id


MAL_CLIENT_ID = load_mal_client_id()


def step1_generate_url():
    auth_url = (
        "https://myanimelist.net/v1/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={MAL_CLIENT_ID}"
        f"&code_challenge={CODE_VERIFIER}"
        f"&code_challenge_method=plain"
        f"&redirect_uri=http://localhost"
    )

    print("\n" + "=" * 60)
    print("STEP 1 COMPLETE")
    print("=" * 60)
    print("\nOpen this URL in your browser (on any device):\n")
    print(auth_url)
    print("\n" + "=" * 60)
    print("Log in to MAL if asked, then click Allow.")
    print("You'll land on a page that won't load (localhost). That's fine.")
    print("Copy the FULL url from the address bar, e.g.:")
    print("  http://localhost/?code=XXXXXXXXXX")
    print("\nThen re-run this workflow with that URL as the")
    print("'mal_redirect_url' input to complete setup.")
    print("=" * 60 + "\n")

def step2_exchange_code(redirected_url):
    if "code=" not in redirected_url:
        print("ERROR: No code found in the URL you pasted.")
        sys.exit(1)

    code = redirected_url.split("code=")[-1].split("&")[0]

    print("Exchanging code for token...")
    r = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id":     MAL_CLIENT_ID,
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  "http://localhost",
            "code_verifier": CODE_VERIFIER,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )

    if r.status_code != 200:
        print(f"ERROR: {r.status_code} — {r.text}")
        sys.exit(1)

    td = r.json()
    td["expires_at"] = time.time() + td.get("expires_in", 3600)

    with open(TOK_F, "w") as f:
        json.dump(td, f)

    print("\n" + "=" * 60)
    print("SUCCESS — mal_token.json created.")
    print("MAL setup complete. This file will now be committed.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    redirect_url = os.environ.get("MAL_REDIRECT_URL", "").strip()
    if redirect_url:
        step2_exchange_code(redirect_url)
    else:
        step1_generate_url()
