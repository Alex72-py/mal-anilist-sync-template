# MAL → AniList Sync Bot (Template)

Syncs your MyAnimeList anime + manga list to AniList automatically.
Runs entirely on GitHub Actions — no server, no phone, no local machine
needed once it's set up.

This is a **template repository**. Click **"Use this template"** above to
create your own independent copy, with your own git history and your own
GitHub Actions minutes — completely separate from this repo and from anyone
else who's used the template.

---

## ⚠️ Before you do anything else, read this

### 1. Keep your created repo **private**

This template repo is public so people can find and use it. But **the repo
you create from it should be set to private** as soon as you create it.

Once set up, your repo stores your live MAL and AniList OAuth tokens as
plain committed files (`mal_token.json`, `anilist_token.json`) — there are
no GitHub Secrets involved anywhere in this project, by design. That keeps
the setup simple and fully editable from the GitHub web UI, but it also
means: **if your repo is public, your tokens are exposed to anyone.**
Treat your created repo the same way you'd treat a file full of passwords.

### 2. You must register your own OAuth apps

MAL and AniList API credentials are tied to whoever registers them — there's
no way around each user doing this themselves, and it only takes about two
minutes per provider:

- **MyAnimeList**: [myanimelist.net/apiconfig](https://myanimelist.net/apiconfig) — create an app, note the **Client ID**.
- **AniList**: [anilist.co/settings/developer](https://anilist.co/settings/developer) — create an app, note the **Client ID** and **Client Secret**.

**For both**, set the redirect URI to exactly:

```
http://localhost
```

(You'll get redirected to a page that fails to load during setup — that's
expected, you just need the URL from your browser's address bar.)

---

## Setup

### Step 1 — Use this template

Click **"Use this template"** at the top of this page → create a new
repository → **set it to Private** (see above) → clone or just work in the
GitHub web UI, whichever you prefer.

### Step 2 — Fill in `config.json`

Everything the bot needs lives in one file, `config.json`:

```json
{
  "mal_client_id": "",
  "anilist_client_id": "",
  "anilist_client_secret": "",
  "mal_username": "",
  "sync_interval_days": 23
}
```

Fill in your 4 values from Step "0" above, either way:

- **Path A — hand-edit**: Open `config.json` in the GitHub web UI (or
  clone locally), fill in the 4 fields, commit.
- **Path B — guided workflow**: Go to the **Actions** tab → **"Setup -
  Config"** → **Run workflow** → fill in the 4 fields in the form → Run.
  This writes and commits `config.json` for you.

Both paths produce the same file, so everything downstream works
identically either way. `sync_interval_days` controls how often a sync
actually happens (in days, not calendar months) — 23 is a sane default,
edit it directly in `config.json` any time.

### Step 3 — Authorize with MAL

Go to **Actions → "Setup - MAL OAuth Token" → Run workflow**, leave the
input blank, and run it.

- Open the Actions log for that run. It prints an authorization URL —
  open it in your browser, log into MAL, click **Allow**.
- You'll land on a broken `http://localhost/?code=...` page. That's fine —
  copy the **full URL** from your address bar.
- Go back to **Actions → "Setup - MAL OAuth Token" → Run workflow** again,
  this time pasting that full URL into the input field, and run it.
- This commits `mal_token.json` to your repo. MAL setup is done.

### Step 4 — Authorize with AniList

Same two-pass dance, using **"Setup - AniList OAuth Token"** instead:

- Run it once with no input → get the auth URL from the log → open it,
  log into AniList, click **Authorize**.
- Copy the full `http://localhost/?code=...` URL you land on.
- Run the workflow again, pasting that URL into the input.
- This commits `anilist_token.json`. AniList setup is done.

### Step 5 — Done

From here on, **"MAL to AniList Sync"** runs automatically once a day
(checking in, but only actually syncing every `sync_interval_days` days per
your config). You can also trigger it manually any time from the Actions
tab. Logs are appended to `anilist_sync_log.txt` in the repo after each run.

---

## How the sync works

For each of your anime and manga lists on MAL, every entry is looked up on
AniList by MAL ID:

- Not found in AniList's database at all → skipped
- Found in AniList's database, but not on your AniList list → **added**,
  using MAL's status/progress/score
- On both lists, and your AniList progress is behind MAL → **updated**
- On both lists, and AniList is already caught up → left alone

Status mapping: `watching`/`reading` → `CURRENT`, `completed` →
`COMPLETED`, `on_hold` → `PAUSED`, `dropped` → `DROPPED`,
`plan_to_watch`/`plan_to_read` → `PLANNING`.

## Files

| File | Purpose |
|---|---|
| `config.json` | Your credentials + sync interval — the only file you need to edit |
| `mal_to_anilist.py` | Main sync script |
| `setup_mal_token.py` / `setup_anilist_token.py` | One-time OAuth helpers (run via their workflows, not directly) |
| `anilist_sync_log.txt` | Running log, created after your first sync |
| `.github/workflows/sync.yml` | Daily scheduled sync job |
| `.github/workflows/setup_config.yml` | Guided form to fill in `config.json` |
| `.github/workflows/setup_mal.yml` / `setup_anilist.yml` | One-time OAuth setup jobs |

## Troubleshooting

If a workflow run fails, check the Actions log first — both the sync script
and the setup scripts print a clear explanation (not just a stack trace)
when `config.json` is missing, invalid, or incomplete. The most common
causes are: `config.json` not filled in yet, or running the MAL/AniList
setup workflows before `config.json` has the corresponding client ID/secret.

## License

MIT — see [LICENSE](LICENSE).
