# Deploying ManuBot on Render — Full Tutorial (from zero)

This guide takes you from nothing to a live, always-on Discord bot on
[render.com](https://render.com). **Plan for it to cost ~\$7/mo** (a Render
"Starter" background worker). A Discord bot holds a permanent websocket
connection, so the free tier won't work (it sleeps and kills the bot).

> You will need: a GitHub account, a Discord account and a Groq API key.

---

## Table of contents

1. [Get the pieces](#1-get-the-pieces)
2. [Create the Discord application & invite the bot](#2-create-the-discord-application--invite-the-bot)
3. [Put the bot code on GitHub](#3-put-the-bot-code-on-github)
4. [Deploy on Render](#4-deploy-on-render)
5. [First boot & verification](#5-first-boot--verification)
6. [Seed it with training data](#6-seed-it-with-training-data)
7. [Updating the bot](#7-updating-the-bot)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Get the pieces

### 1a. The code
You already have the finished ManuBot project on your machine. Make sure it
includes: `bot.py`, `core/`, `cogs/`, `training/`, `utils/`, `requirements.txt`,
`.gitignore`.

### 1b. A Groq API key
Go to <https://console.groq.com/keys> → **Create API Key** → copy the `gsk_...` value.
(It costs only if you spend quota; Groq has a generous free tier.)

### 1c. The bot's server ID and your user ID
- Open Discord → **Settings → Advanced → enable Developer Mode**.
- Right-click your **server name** → **Copy Server ID** → that's `GUILD_ID`.
- Right-click your **own avatar** → **Copy User ID** → that's `OWNER_IDS`.

---

## 2. Create the Discord application & invite the bot

1. Go to <https://discord.com/developers/applications> → **New Application** → name
   it (e.g. `ManuBot`) → Create.
2. In the left sidebar, click **Bot**:
   - **Reset Token** → **Copy** — this is your `DISCORD_TOKEN`. (Treat it like a password; it's shown once.)
   - Scroll to **Privileged Gateway Intents** and enable **two** switches:
     - `MESSAGE CONTENT INTENT`  ← absolutely required (the bot reads messages)
     - `SERVER MEMBERS INTENT`   ← required (for `/train` and `clone`)
   - Click **Save Changes**.
3. Click **OAuth2 → URL Generator**:
   - Check **Scopes:** `bot` and `applications.commands`
   - Check **Bot Permissions:** *Send Messages*, *Embed Links*, *Read Message
     History*, *Add Reactions*, *Attach Files*, *Manage Messages*, *View Channels*
   - Copy the generated URL at the bottom, open it in your browser, and add the
     bot to your server.
   - (You can also use the direct form:
     `https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147607680&scope=bot%20applications.commands`
     replacing `YOUR_CLIENT_ID` with the Application ID on the **General
     Information** page.)

---

## 3. Put the bot code on GitHub

Render pulls the code from GitHub, so the project must live in a repo.

```bash
# at the project root (where bot.py is)
git init
git add .
git commit -m "ManuBot overhaul"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/manubot.git   # create the repo first on github.com
git push -u origin main
```

**Important:** the `.gitignore` already excludes `env` (your secrets) and
`chroma_db*` (the local database), so **neither reaches GitHub**. The bot will
build its database from scratch after deploy (`/train import`), which is
covered in step 6. Also verify nothing sensitive is in the repo:

```bash
git ls-files | grep -E "^(env|\.env)$"   # should output nothing
```

---

## 4. Deploy on Render

### 4a. Create the service
1. Create an account at <https://render.com> (GitHub login is fine) and verify
   the email. You'll attach a card when upgrading (needed for background workers).
2. Click **New +** → **Background Worker**. (Not "Web Service" — a background
   worker doesn't require a web port and won't sleep.)
3. Connect GitHub and pick your `manubot` repo.

### 4b. Service settings
Set these exactly (paths are case-sensitive):

| Setting | Value |
|---------|-------|
| **Name** | `manubot` |
| **Runtime / Environment** | Python 3 (auto-detected, keep native build pack) |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -u bot.py` (`-u` keeps logs unbuffered) |
| **Instance Type** | Starter (~\$7/mo; required for a persistent bot) |

### 4c. Environment variables
| Variable | Value |
|----------|-------|
| `DISCORD_TOKEN` | the bot token from step 2 |
| `GROQ_API_KEY` | the `gsk_...` key from step 1 |
| `GUILD_ID` | your server ID (fast command sync + required for immediate slash registration) |
| `OWNER_IDS` | your user ID (allows `/admin`) |
| `DATA_DIR` | `/data` (**critical** — this is where the DB/config live) |

### 4d. Persistent disk
Still in the service settings, click **Add Disk**:
- **Mount Path:** `/data`
- **Size:** 1 GB is plenty to start (the vector DB grows slowly).

This is what keeps `chroma_db/` and the JSON stores alive across restarts and
deploys. The bot automatically writes everything under `DATA_DIR=/data` and also
sets `HOME=/data` so Chroma's embedding model cache lives on the disk too.

### 4e. Deploy
Click **Create Background Worker**. Render will build (install deps) and then
start the bot. First build usually takes 2–5 minutes.

---

## 5. First boot & verification

1. Open the service → **Logs** tab. You should eventually see:
   ```
   INFO manubot: Data directory: /data
   INFO manubot: Logged in as ManuBot#1234 (ID 1234567890)
   INFO manubot: Guilds: Your Server
   INFO manubot: Embedder warm-up complete
   INFO manubot: Synced commands to guild 999999999999999999
   ```
2. First startup also downloads Chroma's ~80MB embedding model and starts
   background-work on existing rows. **Give it a few minutes** — if the DB is
   empty this is fast.
3. Back in Discord: type `/help`. If slash commands don't appear, press Ctrl+R
   or re-enter the channel — new commands take a moment to register.

At this point the bot is online but has **no personalities yet** — you'll see
`/personality list` show only the empty `default`. Seed it below.

---

## 6. Seed it with training data

The local database was not pushed to GitHub, so the server copy starts empty.
Choose one (or both):

### Option A — rebuild from Discord (easiest, no files)
```text
/personality clone bigbhav @BigBhav      # creates a target personality
/train import bigbhav @BigBhav           # optionally: @BigBhav, default channel scope
```
`/train import` scrapes the member's message history from the visible channels
and embeds it into the collection. Run `/stats` to watch it grow.

### Option B — migrate your existing `chroma_db`
If you want your exact local database on the server:

1. In Render, open your service → **Shell** (top-right, available on paid
   instances).
2. Get your `chroma_db.zip` onto the server, e.g. host it somewhere with a direct
   download link (Dropbox, transfer.sh, etc.), then inside the shell:
   ```bash
   cd /data
   wget -O chroma_db.zip "https://your.link/chroma_db.zip"   # or curl -L -o
   unzip chroma_db.zip -d /data/chroma_db
   rm chroma_db.zip
   ls /data/chroma_db
   ```
   The zip must contain the `chroma.sqlite3` file (like your original archive did).
3. Restart the service from the Render dashboard. On boot the bot will
   `warm_up()` — the first query re-computes/indexes and can take a few minutes
   on a large collection.

> Tip: keep a small disk (1GB) if you mostly auto-train, or 2GB+ if you import
> many long histories.

---

## 7. Updating the bot

Every `git push` to `main` triggers an automatic re-deploy. During deploys:
- The disk at `/data` is preserved — your trained personalities, archive lore
  and conversation memory survive.
- The bot re-downloads nothing except new code (the embedding model stays in
  `/data/.cache`).
- If you want zero-downtime you don't need it here — a transient restart in the
  middle of the night is fine.

Local run stays the same: `python bot.py`.

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `Missing DISCORD_TOKEN` | Env var not attached to the service — check step 4c |
| `403 Forbidden` / "MESSAGE CONTENT" warning on login | Did not enable **Message Content Intent** in the Dev Portal → enable it → **Deploy** |
| `401 Unauthorized` on login | Token was rotated or pasted with trailing space — reset token, redeploy |
| Slash commands missing | Restart with `GUILD_ID` set, or wait for global sync (can take up to 1 hour) |
| Bot goes offline randomly | You're on a **free web service** that sleeps — use a Background Worker (paid) |
| `/train import` is very slow | First run downloads the embedding model and embeds thousands of rows — watch logs, it's normal |
| `/stats` shows 0 messages | No training data yet — run `/train import` or `/train watch #channel` |
| Help or chat reply 500s | Groq key invalid or quota exceeded — check console.groq.com and the service logs |
| "unhandled command error" in logs | Screenshot/quote the line — usually an invalid config value or missing permission |
| Disk filling up | Increase disk size in service settings (Render restarts the service automatically) |

---

## Cost & plan summary

| Item | Cost |
|------|------|
| Render Background Worker (Starter) | ~\$7/mo (includes 512MB RAM, 25GB storage, persistent disk up to 10GB) |
| Groq API | Free tier unless very heavy use |
| Discord | Free |

**Run order to replicate:** GitHub repo → Render Background Worker → env vars →
disk at `/data` → deploy → `/train import` → `/stats` to verify → done.