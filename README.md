# ManuBot

An advanced Discord bot that **imitates a real person's texting style**. It learns from
actual Discord messages, stores them in a vector database, and generates responses that
match someone's tone, slang, punctuation, and message length.

Built on **discord.py**, **ChromaDB** (vector search) and **Groq** (fast inference).

---

## Features

| Area | What it does |
|------|--------------|
| **Chat** | `/chat <msg>` talks to the bot; it replies as the active personality. Also auto-replies to anyone who mentions it, and can auto-reply in watched channels in immersive mode. |
| **Multi-personality** | `/personality add|clone|switch|remove|info|list` - the bot can imitate several different people and you can swap between them per server. |
| **Auto-training** | `/train watch #channel` - the bot silently learns every qualifying message posted there. `/train import <@member>` bulk-imports someone's entire message history in one shot. |
| **Archive & lore** | `/archive remember|recall|recent` - a permanent semantic-memory archive. `/incidents add|list|search|remove` - server inside-jokes that get injected into the bot's context so replies feel "in the know". |
| **Feedback loops** | React on any bot reply: 👍 keep/Learn, 🫤 meh, 👎 delete from training data, 📌 archive it, 🔄 regenerate it. This is how the bot self-improves. |
| **Configuration** | `/config` - change model, temperature, max tokens, cooldown, auto-reply toggles, memory length. All per server. |
| **Stats** | `/stats` - knowledge-base size, uptime, activity, active model. |
| **Admin** | `/admin cleanup|drop-collection|collections|reload|purge-archive` (owner-only). |
| **Safety** | Per-user cooldowns, response length caps, admin-gated settings, graceful rate-limit handling and retries. |

## Quick Start (local)

```bash
# 1. install
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt

# 2. configure
copy .env.example .env          # then fill in your tokens
# legacy: the repo also reads a plain `env` file if present

# 3. run
python bot.py
```

Required env vars:

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `DISCORD_TOKEN` | yes | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
| `GROQ_API_KEY` | yes | Key from [console.groq.com](https://console.groq.com) |
| `GUILD_ID` | no | Server ID; commands sync instantly to this server on startup |
| `OWNER_IDS` | no | Comma-separated user IDs allowed to run `/admin` |
| `DATA_DIR` | no | Directory for `chroma_db/`, config and history. Defaults to the project folder. **Set to your persistent volume path on Render/Railway/Fly (e.g. `/data`).** |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` / `WARNING` |

### First run skeleton

1. Rename `env` → `.env` (or keep both - the bot reads either).
2. `python bot.py` - the bot creates the `default` personality pointing at the `friend_messages` collection.
3. In Discord, run `/personality list` to see the current state.
4. Train it on someone:
   - `/personality clone bigbhav @BigBhav` then `/train import @BigBhav` - pulls their whole message history, or
   - `/train watch #general @BigBhav` - learns from them live and permanently.
5. `/config` to tune temperature/model, `/stats` to watch it grow.

## Slash commands

```
/chat <message>                          talk to the bot (replies as active personality)
/forget                                  clear this channel's conversation memory
/personality list | info | add | switch | clone | remove
/train import <@member> | watch #ch [@u] | unwatch #ch | status | prune
/archive remember <text> | recall <q> | recent | delete
/incidents list | add <name> <desc> | remove <name> | search <text>
/config [<key> <value>]                  show or change server settings (admin)
/models                                  list Groq models
/stats                                   bot statistics
/help                                    this list
/admin cleanup | collections | drop-collection <name> | reload | purge-archive   (owner only)
```

### Reaction feedback on bot replies

| Reaction | Effect |
|----------|--------|
| 👍 / 💯 / ❤️ | boosts the reply's quality in training data |
| 🫤 | marks "meh" (mid quality) |
| 👎 | removes the reply from the training database |
| 📌 | archives the reply permanently |
| 🔄 | regenerates a new reply to the same message |

## Project layout

```
bot.py                 entry point: services, command sync, startup
core/                  config, database (ChromaDB), Groq client, memory, personalities, prompt builder
cogs/                  chat, personality, training, archive, config, stats, admin, help
training/              message scraper + embedder used by /train import
utils/                 embeds (+ pagination), permission checks, helpers
check_db.py            inspect collections            (python check_db.py)
db_cleanup.py          purge generated replies        (python db_cleanup.py [collection])
test_query.py          try semantic search in terminal
generate_reply.py      test the mimic pipeline in terminal
```

---

## Deployment

The recommended way is a small always-on VPS with a **persistent disk**. The bot needs a
persistent filesystem for `chroma_db/` (vector data) and the JSON config/history files.
Discord bots keep a long-lived websocket connection, so a plain HTTP host won't work.

### Option A - Railway (recommended, easiest free-ish start)

1. Create an account at [railway.app](https://railway.app) and install the CLI.
2. Push this repo to GitHub, then in Railway: **New Project → Deploy from GitHub repo.**
3. Set the [environment variables](#required-env-vars) (`DISCORD_TOKEN`, `GROQ_API_KEY`) in **Dashboard → Variables**. `GUILD_ID` is highly recommended.
4. Add a **volume** mounted at `/app/chroma_db` (this persists your vector DB across deploys). Small free/5$ instances are fine.
5. Railway auto-detects Python (`requirements.txt`) — no Dockerfile needed if you prefer.
6. Seed the database:
   - Easiest: run `/train import @YourTarget` to build it from scratch on the server, or
   - Upload your existing `chroma_db/` into the volume once.

### Option B - Render

> Full zero-to-deployed walkthrough: **see [DEPLOY_RENDER.md](DEPLOY_RENDER.md)**.

1. [render.com](https://render.com) → **New Web Service** → connect the repo.
2. Build command: `pip install -r requirements.txt` — Start command: `python bot.py`.
3. Add env vars. On a paid instance ($7/mo) enable **Persistent Disk** (e.g. mount to `/opt/render/project/src`) so `chroma_db/` survives restarts.
4. Render Free tier has no persistent disk and sleeps the service, which breaks a Discord bot - use it for experiments only.

### Option C - Fly.io

1. `flyctl launch` → set `internal_port` to anything (the bot doesn't listen), or use the included `Dockerfile`.
2. `flyctl volumes create data --size 3` and mount it at `/app/chroma_db` via `fly.toml`:
   ```toml
   [mounts]
     source = "data"
     destination = "/app/chroma_db"
   ```
3. `flyctl secrets set DISCORD_TOKEN=... GROQ_API_KEY=...`
4. `flyctl deploy`

> **Tip:** the first time the bot makes a semantic query it downloads Chroma's embedding
> model (~80MB) into `~/.cache/chroma` and computes embeddings for existing rows, which
> can take a few minutes on a big database. The bot warms this up automatically at
> startup (`db.warm_up()`), so give it a minute before assuming it's broken.

### Why NOT Cloudflare Workers

Cloudflare Workers serve **HTTP requests only**, while a Discord bot needs a persistent
**gateway websocket** to receive `message` and `reaction` events. Running the full bot on
Workers isn't possible. Two viable compromises:

1. **Slash-command-only bot via Workers (D1/KV):** a full JS/TS rewrite that responds to
   slash command *interactions* over HTTP (Discord supports this for apps). You lose
   on_message auto-reply, auto-training, reaction feedback, and real-time personality
   learning - the heart of this bot. D1 (SQLite) can replace ChromaDB with crude
   `LIKE`/FTS queries, and KV can store conversation history.
2. **Workers as a façade:** run the real bot on a VPS and put a Workers route in front
   of a public health/stats endpoint for free caching & DDoS protection. Best of both.

For `ManuBot` as designed, **a VPS is the right choice**.

### Keeping it alive cheap

- Railway/Fly.io instances run continuously (no cold starts).
- Render will sleep free instances - it's fine if you only turn the bot on occasionally.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Missing DISCORD_TOKEN` | You need a `Discord_TOKEN` variable in `.env`/`env` or the host's env settings. |
| `401: Unauthorized` on startup | The token needs the **Bot** scope + `MESSAGE CONTENT` privileged intent enabled in the developer portal. |
| Slash commands not appearing | Restart with `GUILD_ID` set; commands sync to that server at startup. |
| First `/train import` is slow | It's downloading the embedding model / crunching embeddings. Watch the log. |
| `/config model` invalid | Run `/models` and use an exact id (e.g. `qwen/qwen3.8-27b`). |

## License

MIT - do whatever, but the funny incidents stay.