# OpenClaw Mentor Assistant

A self-hosted personal mentor that runs on a Hetzner VPS (or similar Linux server), reachable only over **Tailscale**. It combines:

- **Telegram** — primary interface for memory, commands, and mentorship chat
- **Claude Haiku (Anthropic)** — conversational mentor with tool access to your memory
- **SQLite** — durable storage for goals, plans, reminders, and facts
- **Modular trigger framework** — location events (Home Assistant), scheduled reminders, and extensible rules
- **Home Assistant** — optional iPhone location tracking and zone automations

There are no inbound public webhooks. Telegram uses outbound long-polling; Home Assistant calls a local webhook on the same machine.

---

## Table of contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Server setup (start to finish)](#server-setup-start-to-finish)
4. [Environment variables](#environment-variables)
5. [Project layout](#project-layout)
6. [Operations](#operations)
7. [Telegram interface](#telegram-interface)
8. [Memory system](#memory-system)
9. [Mentorship (LLM)](#mentorship-llm)
10. [Reminders and scheduling](#reminders-and-scheduling)
11. [Trigger framework](#trigger-framework)
12. [Home Assistant integration](#home-assistant-integration)
13. [Security model](#security-model)
14. [Backup and recovery](#backup-and-recovery)
15. [Troubleshooting](#troubleshooting)
16. [Dashboard (mobile web UI)](#dashboard-mobile-web-ui)
17. [Extending the system](#extending-the-system)

---

## Architecture

```
┌─────────────────┐     Tailscale      ┌──────────────────────────────────────────┐
│  iPhone         │◄──────────────────►│  Hetzner VPS                             │
│  - Telegram     │                    │                                          │
│  - HA Companion │                    │  ┌─────────────┐    ┌───────────────┐    │
└────────┬────────┘                    │  │ mentor-ha   │    │ mentor-core   │    │
         │                             │  │ (HA, :8123) │    │ Telegram poll │    │
         │ HTTPS (Telegram cloud)      │  │ host network│    │ FastAPI :8000 │    │
         └─────────────────────────────┼─►│             │───►│ SQLite memory │    │
                                       │  └─────────────┘    └───────┬───────┘    │
                                       │         │ webhook           │            │
                                       │         └───────────────────┘            │
                                       │                    │ Anthropic API       │
                                       └────────────────────┼─────────────────────┘
                                                            ▼
                                                   Claude Haiku
```

### Data flows

| Path | Direction | Purpose |
|------|-----------|---------|
| User → Telegram → mentor-core | Inbound (poll) | Commands, chat, memory CRUD |
| mentor-core → Anthropic | Outbound HTTPS | Mentorship + memory tools |
| mentor-core → Telegram | Outbound HTTPS | Replies, triggers, reminders |
| HA → `127.0.0.1:8000` | Local HTTP | Zone enter/exit webhooks |
| Schedule loop (internal) | In-process | Due reminders → trigger router → Telegram |

### Containers

| Service | Image / build | Network | Ports |
|---------|---------------|---------|-------|
| `mentor-ha` | `ghcr.io/home-assistant/home-assistant:stable` | `host` | `8123` on all host interfaces |
| `mentor-core` | Built from `./app` | bridge (default) | `127.0.0.1:8000` → container `8000` |

Home Assistant uses **host networking** so it can see Tailscale and local interfaces correctly. The mentor webhook is exposed on the host at `127.0.0.1:8000` (not on the public internet).

---

## Prerequisites

### Server (Hetzner or any Linux VPS)

- Ubuntu/Debian-style system with root or sudo
- [Docker](https://docs.docker.com/engine/install/) and [Docker Compose v2](https://docs.docker.com/compose/install/)
- Enough disk for HA (~2 GB image) and SQLite data

### Accounts and keys

| Item | How to obtain |
|------|----------------|
| **Tailscale** | [tailscale.com](https://tailscale.com) — install on server and phone, same tailnet |
| **Telegram bot** | Message [@BotFather](https://t.me/BotFather) → `/newbot` → save token |
| **Telegram chat ID** | Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id` |
| **Anthropic API key** | [console.anthropic.com](https://console.anthropic.com) |

### Phone

- **Tailscale** app — always-on VPN recommended
- **Telegram** — chat with your bot (only chat authorized by `TELEGRAM_CHAT_ID`)
- **Home Assistant Companion** (optional) — for location-based triggers

---

## Server setup (start to finish)

### 1. Install Tailscale on the server

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
```

Note this IPv4 (e.g. `100.x.y.z`). You will use it to open Home Assistant from your phone.

Allow Tailscale through the firewall if you use UFW:

```bash
sudo ufw allow in on tailscale0
```

### 2. Clone or copy the project

```bash
cd /root
# If using git:
# git clone <your-repo> openclaw-mentor
cd openclaw-mentor
```

### 3. Configure environment

```bash
cp .env.template .env
nano .env
```

Set every value (see [Environment variables](#environment-variables)). **Critical:** `TAILSCALE_IP` must match `tailscale ip -4` on this machine (used for documentation and optional binding; HA listens on all interfaces in host mode).

Generate a webhook secret:

```bash
openssl rand -hex 16
# Put result in HA_WEBHOOK_SECRET in .env
```

### 4. Configure Home Assistant secrets

Edit `homeassistant/config/secrets.yaml`:

```yaml
mentor_webhook_secret: "Bearer YOUR_HA_WEBHOOK_SECRET_FROM_ENV"
```

The value must be the literal string `Bearer ` plus the same secret as `HA_WEBHOOK_SECRET` in `.env`.

### 5. Build and start services

```bash
docker compose up -d --build
docker compose ps
docker logs mentor-core --tail 30
docker logs mentor-ha --tail 30
```

Expected mentor-core log lines:

- `Applying migration v1` (first run only)
- `Loaded N trigger rules`
- `Telegram polling started`
- `Webhook server starting on :8000`
- `Schedule adapter started`

Health check:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}
```

### 6. Complete Home Assistant onboarding (browser)

On a device with Tailscale connected:

1. Open `http://<TAILSCALE_IP>:8123` (e.g. `http://100.x.y.z:8123`)
2. Create your owner account in the web UI
3. Finish location, analytics, and integration steps
4. Install **Home Assistant Companion** on iPhone and add the same URL
5. Enable location permissions for the Companion app

**Do not** use the Companion app for the very first account creation if you see `OnboardingAuthError` — use Safari first, then add the server in the app.

Optional: set internal/external URL in HA **Settings → System → Network**:

- Internal URL: `http://<TAILSCALE_IP>:8123`
- External URL: same (Tailscale-only deployment)

### 7. Wire Home Assistant to mentor-core (location triggers)

After HA onboarding, add mentor webhook support to `homeassistant/config/configuration.yaml`:

```yaml
rest_command:
  mentor_location:
    url: "http://127.0.0.1:8000/webhooks/ha/location"
    method: POST
    headers:
      Authorization: !secret mentor_webhook_secret
    content_type: "application/json"
    payload: '{"event": "{{ event }}", "zone": "{{ zone }}"}'
```

Create zones in HA (**Settings → Areas & zones**) named consistently with your trigger rules (e.g. `Gym`, `Home`, `Work` — automations should send lowercase zone names).

Example `homeassistant/config/automations.yaml` (adjust `device_tracker` entity to match your phone):

```yaml
- id: mentor_zone_enter
  alias: Mentor - zone enter
  trigger:
    - platform: zone
      entity_id: device_tracker.<your_iphone_entity>
      zone: zone.gym
      event: enter
    - platform: zone
      entity_id: device_tracker.<your_iphone_entity>
      zone: zone.home
      event: enter
    - platform: zone
      entity_id: device_tracker.<your_iphone_entity>
      zone: zone.work
      event: enter
  action:
    - service: rest_command.mentor_location
      data:
        event: enter
        zone: "{{ trigger.zone.attributes.friendly_name | lower }}"

- id: mentor_zone_exit
  alias: Mentor - zone exit
  trigger:
    - platform: zone
      entity_id: device_tracker.<your_iphone_entity>
      zone: zone.home
      event: leave
  action:
    - service: rest_command.mentor_location
      data:
        event: exit
        zone: "{{ trigger.zone.attributes.friendly_name | lower }}"
```

Reload automations: **Developer tools → YAML → Automations → Reload**, or restart `mentor-ha`.

Test from the server:

```bash
curl -s -X POST http://127.0.0.1:8000/webhooks/ha/location \
  -H "Authorization: Bearer YOUR_HA_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"event": "enter", "zone": "gym"}'
```

You should receive a Telegram message if rules match (see default `app/config/triggers.yaml`).

### 8. Verify Telegram

Message your bot:

```
/timezone America/New_York
/status
goal: Test goal from setup
/list
```

You should get replies. If not, see [Troubleshooting](#troubleshooting).

### 9. Customize mentor persona (optional)

Edit `app/config/profile.json`:

```json
{
  "persona": "You are a senior, analytical mentor...",
  "mentor_knowledge_base": [
    "Prefers morning deep work",
    "Training for half marathon"
  ]
}
```

Restart mentor-core: `docker compose restart mentor-core`

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TAILSCALE_IP` | Yes | Server Tailscale IPv4 (`tailscale ip -4`) |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your numeric Telegram user/chat ID (only this chat is honored) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude Haiku |
| `HA_WEBHOOK_SECRET` | Yes | Shared secret; HA sends `Authorization: Bearer <secret>` |
| `DASHBOARD_PIN` | Yes | PIN for the mobile web dashboard (sent as `X-Dashboard-Pin` header) |
| `USER_TIMEZONE` | Yes | IANA timezone, e.g. `America/New_York` (default for new reminders) |

`mentor-core` reads these via `env_file: .env` in Docker Compose. They are not committed to git (see `.gitignore`).

---

## Project layout

```
openclaw-mentor/
├── docker-compose.yml          # mentor-ha + mentor-core
├── .env                        # secrets (not in git)
├── .env.template
├── data/                       # mentor.sqlite (persisted, gitignored)
├── homeassistant/config/       # HA configuration & .storage
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # entrypoint
│   ├── telegram_handler.py     # commands & message routing
│   ├── llm_client.py           # Anthropic + memory tools
│   ├── api/
│   │   └── dashboard.py        # REST API for mobile dashboard
│   ├── static/                 # mobile web dashboard (vanilla JS)
│   │   ├── index.html
│   │   ├── css/dashboard.css
│   │   └── js/{api,app,components}.js
│   ├── config/
│   │   ├── profile.json        # mentor persona
│   │   └── triggers.yaml       # event → reaction rules
│   ├── memory/                 # SQLite repository
│   └── triggers/               # router, reactions, adapters
└── README.md
```

---

## Operations

### Start / stop / restart

```bash
cd /root/openclaw-mentor

docker compose up -d          # start
docker compose down           # stop
docker compose restart mentor-core
docker compose restart home-assistant
docker compose up -d --build  # rebuild after code changes
```

### Logs

```bash
docker logs -f mentor-core
docker logs -f mentor-ha
```

### Update application code

```bash
cd /root/openclaw-mentor
# edit files under app/
docker compose build mentor-core
docker compose up -d mentor-core
```

Config and triggers are mounted from `app/config/` — restart after editing `profile.json` or `triggers.yaml`.

---

## Telegram interface

All interaction assumes a **single authorized user** (`TELEGRAM_CHAT_ID`). Messages from other chats are ignored.

### Slash commands

| Command | Syntax | Description |
|---------|--------|-------------|
| `/add` | `/add <type> <title>` | Create item. Types: `goal`, `plan`, `reminder`, `fact` |
| `/list` | `/list` or `/list goal` or `/list --tag=gym` | List active items (max 25) |
| `/show` | `/show <id>` | Full details for one item |
| `/done` | `/done <id>` | Mark item completed |
| `/cancel` | `/cancel <id>` | Mark item cancelled |
| `/snooze` | `/snooze <id> <iso_datetime>` | Reschedule reminder, e.g. `2026-05-20T14:00:00` |
| `/timezone` | `/timezone` or `/timezone America/Chicago` | Get or set reminder timezone |
| `/status` | `/status` | Short summary of active memory (also injected into LLM context) |

**Examples:**

```
/add goal Ship openclaw-mentor as daily driver
/add plan Update resume for backend roles
/list plan
/show 3
/done 5
/timezone America/New_York
```

### Quick capture (prefix lines)

Messages starting with these prefixes are saved **without** calling the LLM:

| Prefix | Creates type |
|--------|----------------|
| `goal:` | goal |
| `plan:` | plan |
| `remind:` | reminder (title only; no automatic time) |
| `fact:` | fact |
| `remember:` | fact |

**Examples:**

```
goal: Land senior backend role by September
plan: Finish MA453 homework 12 tonight
fact: Gym Mon/Wed/Fri mornings
remember: Prefer direct, actionable mentor tone
```

### Free-form chat (mentorship)

Any other text is sent to **Claude Haiku** with:

- Persona from `profile.json`
- Active memory summary
- Tools: `memory_create`, `memory_list`, `memory_update`, `memory_complete`

**Examples:**

```
What should I focus on today given my goals?
Remind me tomorrow at 8am to review flashcards
Add a plan: email professor about extension
Mark item 4 as done
```

The model may create reminders **with** `due_at` when you ask in natural language — this is the recommended way to set timed reminders.

---

## Memory system

### Item types

| Type | Purpose |
|------|---------|
| `goal` | Longer-term outcomes |
| `plan` | Action items / todos / project steps |
| `reminder` | Time-based notifications (needs `due_at` to fire) |
| `fact` | Stable context for the mentor |

There is no separate `todo` type — use `plan`.

### Status values

| Status | Meaning |
|--------|---------|
| `active` | Visible in lists and mentor context |
| `done` | Completed (reminders also set to `done` after firing) |
| `cancelled` | Dropped |
| `snoozed` | Available in schema; snooze command sets new `due_at` and `active` |

### Database

- **Path (host):** `./data/mentor.sqlite`
- **Path (container):** `/app/data/mentor.sqlite`
- **Schema version:** `PRAGMA user_version = 1`

**Tables:**

- `memory_items` — goals, plans, reminders, facts
- `tags` / `memory_item_tags` — optional tags (LLM can set via `memory_create`; CLI list supports `--tag=`)
- `settings` — e.g. `user_timezone`

### Recommended workflow

1. Set timezone: `/timezone America/New_York`
2. Add 3–5 `goal:` lines
3. Break each into `plan:` items
4. Add `fact:` lines for stable preferences
5. Use natural language for timed reminders
6. Weekly: `/list goal`, `/list plan`, `/done <id>` on completed work

---

## Mentorship (LLM)

- **Model:** `claude-3-haiku-20240307`
- **Config:** `app/config/profile.json`

```json
{
  "persona": "System instructions for tone and domain...",
  "mentor_knowledge_base": ["bullet facts appended to persona"]
}
```

Each chat turn builds a system prompt from persona + up to 20 active memory lines.

### LLM tools

| Tool | Effect |
|------|--------|
| `memory_create` | New item; supports `due_at`, `tags`, `body` |
| `memory_list` | Filter by `type` or `tag` |
| `memory_update` | Change title, body, status, `due_at` |
| `memory_complete` | Mark `done` |

Tool loop runs up to 5 iterations per user message.

---

## Reminders and scheduling

### How firing works

1. A `reminder` row must have `type=reminder`, `status=active`, and `due_at` set (ISO 8601).
2. The **schedule adapter** polls every **60 seconds**.
3. When `due_at` ≤ now (timezone-aware), it emits `reminder.due` to the trigger router.
4. Default rule sends Telegram: `Reminder: {title}`
5. Item is marked **`done`** automatically (one-shot reminders).

### Creating timed reminders

| Method | Sets `due_at`? |
|--------|----------------|
| Natural language to bot | Yes (via `memory_create`) |
| `/add reminder ...` | No |
| `remind: ...` quick capture | No |

**Reliable:** *"Remind me Friday at 6pm to submit homework"*

### Snooze

```
/snooze 7 2026-05-20T14:00:00
```

Sets new `due_at` and keeps status `active`.

### Timezone

- Default from `USER_TIMEZONE` in `.env` at DB init
- Override per user via `/timezone`
- Stored in `settings.user_timezone` and on reminder rows

### Low-cost focus nudges (no API cost)

If you want a periodic "stay on track" message without LLM usage, enable the focus nudge adapter in `.env`:

```bash
FOCUS_NUDGE_ENABLED=true
FOCUS_NUDGE_INTERVAL_MINUTES=120
FOCUS_NUDGE_START_HOUR=8
FOCUS_NUDGE_END_HOUR=22
FOCUS_NUDGE_MAX_PLANS=2
```

Behavior:

- Sends a brief Telegram check-in with your top `goal` and next `plan` items
- Runs only during the configured local-hour window (`/timezone` aware)
- Uses direct Telegram sends (`notify` style), not Anthropic calls

Tip: for effectiveness with low noise, start with every 2 hours and keep only 1 active goal + 2 active plans.

---

## Trigger framework

External events are normalized to a **`TriggerEvent`**, matched against **`app/config/triggers.yaml`**, then handled by **reactions**. Telegram and the LLM are never called directly from adapters.

### TriggerEvent fields

| Field | Example |
|-------|---------|
| `kind` | `location.enter`, `location.exit`, `reminder.due` |
| `source` | `ha`, `schedule` |
| `entity` | `gym`, `7` (reminder id) |
| `payload` | Raw JSON subset |
| `occurred_at` | UTC timestamp |

### Default rules (`app/config/triggers.yaml`)

| Event | Reaction | Effect |
|-------|----------|--------|
| Enter `gym` | `notify` | "At the gym — log your workout?" |
| Exit `home` | `digest` | LLM summary of today's reminders |
| Enter `work` | `notify` | "Arrived at work. Focus mode." |
| `reminder.due` | `notify` | `Reminder: {title}` |

### Reaction types

| Reaction | Behavior |
|----------|----------|
| `notify` | Send Telegram; use `message` or `message_template` with `{title}`, `{entity}`, etc. |
| `ask_llm` | Run Haiku with `prompt` param; send reply to Telegram |
| `digest` | LLM digest using `template` param (e.g. `today_reminders`) |

### Dedupe

Identical `kind` + `entity` within **10 seconds** are ignored (reduces HA bounce).

### HTTP webhook (HA location)

```
POST http://127.0.0.1:8000/webhooks/ha/location
Authorization: Bearer <HA_WEBHOOK_SECRET>
Content-Type: application/json

{"event": "enter", "zone": "gym"}
```

`event`: `enter` or `exit` (also accepts `leave` mapped to exit).  
`zone`: lowercase name matching `triggers.yaml` `entity` field.

---

## Home Assistant integration

### Role of HA

- Track iPhone location via **Companion app**
- Fire automations on zone enter/exit
- Call mentor webhook (mentor logic stays in `mentor-core`)

### Role of Telegram

- Memory, mentorship, timed reminders
- Receive all proactive notifications

### Companion app setup

1. Tailscale on, same tailnet as server
2. Add server: `http://<TAILSCALE_IP>:8123`
3. Sign in with HA credentials
4. Enable location: **Always** (for geofencing)
5. Define zones in HA that match `triggers.yaml` entity names

### Password reset (HA)

```bash
docker exec -it mentor-ha ha auth reset --username YOUR_USERNAME
docker restart mentor-ha
```

Credentials created during automated setup may be stored in `HA_CREDENTIALS.txt` on the server (if present).

---

## Security model

| Control | Implementation |
|---------|----------------|
| No public mentor API | Webhook bound to `127.0.0.1:8000` only |
| HA exposure | Tailscale + optional UFW on `tailscale0`; port `8123` on host |
| Telegram | Only `TELEGRAM_CHAT_ID` processed |
| HA webhook | `Authorization: Bearer` must match `HA_WEBHOOK_SECRET` |
| Secrets | `.env` and `homeassistant/config/secrets.yaml` not in git |

Rotate `HA_WEBHOOK_SECRET` and `TELEGRAM_BOT_TOKEN` if compromised.

### Secret exposure response

If a token appeared in logs, chat, or screenshots:

1. **Stop leaking:** mentor-core sets `httpx`/`telegram` loggers to `WARNING` and redacts secrets in log lines (`app/logging_config.py`).
2. **Rotate local secrets:**
   ```bash
   chmod +x scripts/rotate-secrets.sh
   ./scripts/rotate-secrets.sh
   ```
3. **Revoke Telegram bot token:** [@BotFather](https://t.me/BotFather) → your bot → **API Token** → **Revoke current token**, then:
   ```bash
   NEW_TELEGRAM_BOT_TOKEN='your-new-token' ./scripts/rotate-secrets.sh
   ```
4. **Rotate Anthropic key** in [console.anthropic.com](https://console.anthropic.com), then:
   ```bash
   NEW_ANTHROPIC_API_KEY='your-new-key' ./scripts/rotate-secrets.sh
   ```
5. **Restart and clear container logs** (optional, on server):
   ```bash
   docker compose up -d --build mentor-core
   docker compose restart home-assistant
   sudo truncate -s 0 "$(docker inspect --format='{{.LogPath}}' mentor-core)"
   ```
6. Before git push: `./scripts/verify-no-secrets.sh`

Never commit `.env`, `secrets.yaml`, or `HA_CREDENTIALS.txt`.

---

## Backup and recovery

### Memory database

```bash
cd /root/openclaw-mentor
cp data/mentor.sqlite "data/mentor.sqlite.bak.$(date +%Y%m%d)"
```

Or with sqlite3:

```bash
sqlite3 data/mentor.sqlite ".backup data/backup.sqlite"
```

### Home Assistant

```bash
tar -czf ha-config-backup.tar.gz homeassistant/config/
```

### Restore

Stop containers, restore files, start again:

```bash
docker compose down
# restore data/mentor.sqlite and/or homeassistant/config
docker compose up -d
```

---

## Troubleshooting

### Telegram bot does not reply

```bash
docker ps | grep mentor-core
docker logs mentor-core --tail 50
```

- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Message the bot from the correct Telegram account
- Check Anthropic API key and quota

### `http://<TAILSCALE_IP>:8123` does not load

```bash
tailscale ip -4
docker ps | grep mentor-ha
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8123/
```

- Tailscale connected on client?
- `mentor-ha` running?
- UFW allowing `tailscale0`?

### Companion `OnboardingAuthError` / `unsupportedurl`

- Complete first login in **Safari** at `http://<TAILSCALE_IP>:8123`
- Set HA internal/external URL to that address
- Add server in Companion after web login works

### Location triggers do not fire

```bash
# Test webhook manually
curl -X POST http://127.0.0.1:8000/webhooks/ha/location \
  -H "Authorization: Bearer $HA_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"event":"enter","zone":"gym"}'
docker logs mentor-core --tail 20
```

- `rest_command` and automations configured in HA?
- Zone names lowercase and match `triggers.yaml`?
- `device_tracker` entity correct in automations?

### Reminders never fire

- Reminder must have `due_at` (use natural language, not bare `remind:`)
- Check timezone: `/timezone`
- `docker logs mentor-core | grep -i reminder`

### After code/config changes

```bash
docker compose restart mentor-core
# triggers.yaml and profile.json are mounted — no rebuild needed
```

---

## Dashboard (mobile web UI)

A lightweight single-page dashboard served by the same `mentor-core` container, designed for iPhone Safari over Tailscale.

### Access

Open in Safari on your phone (Tailscale VPN active):

```
http://<TAILSCALE_IP>:8000/
```

On first load you'll be prompted for your dashboard PIN (set in `.env` as `DASHBOARD_PIN`). The PIN is stored in `sessionStorage` (cleared when the tab closes).

### Bookmark as an app icon

1. Open the URL in Safari
2. Share → Add to Home Screen
3. The app uses `apple-mobile-web-app-capable` so it launches in a full-screen chrome-less window with a dark status bar

### Features

| Tab | Function |
|-----|----------|
| **Now** | System status, current zone from Home Assistant, upcoming reminders with snooze, overdue banner |
| **Memory** | Filter by type (goal/plan/reminder/fact), mark items done/cancelled, quick-add form |
| **Triggers** | Read-only view of active trigger rules from `triggers.yaml` |
| **More** | Timezone, health, sign out |

### API endpoints

All under `/api`, protected by header `X-Dashboard-Pin: <DASHBOARD_PIN>`:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/summary` | Counts by type, upcoming reminders, overdue count |
| GET | `/api/memory` | List items (query: `type`, `tag`, `status`) |
| GET | `/api/memory/{id}` | Single item detail |
| PATCH | `/api/memory/{id}` | Update status, due_at, title, body |
| POST | `/api/memory` | Create item `{type, title, body?, due_at?, tags?}` |
| GET | `/api/triggers/rules` | Current trigger rules |
| GET | `/api/status` | Health + last zone event |

### Security

- Only reachable over Tailscale (port bound to `${TAILSCALE_IP}:8000`)
- PIN required for all `/api` routes (`X-Dashboard-Pin` header)
- No public internet exposure

### Environment variable

Add to `.env`:

```
DASHBOARD_PIN=your-dashboard-pin
```

---

## StreetEasy apartment monitor

Polls StreetEasy’s unofficial GraphQL API (`api-v6.streeteasy.com`) for new rentals matching your filters, dedupes by listing ID, and alerts you on Telegram. Optional LLM-drafted broker emails and SMTP send when a broker address appears in the listing text.

**Important:** StreetEasy does not offer a supported public API. Many VPS/datacenter IPs receive **403 Forbidden** from `api-v6.streeteasy.com`; if polls fail, set `STREETEASY_HTTP_PROXY` in `.env` to a residential proxy, or run `mentor-core` on a network StreetEasy accepts. This uses the same GraphQL surface as the website; respect their terms of use. **Request a tour** on StreetEasy still requires a logged-in browser session—the bot sends the link and a draft message; you tap through to submit the official tour request unless SMTP email succeeds.

### Setup

1. Copy the example config:
   ```bash
   cp app/config/streeteasy.yaml.example app/config/streeteasy.yaml
   ```
2. Edit `streeteasy.yaml`: set `enabled: true`, neighborhoods, budget, `move_in_by`, and `outreach` contact fields.
3. Optional: set `STREETEASY_APPLICANT_*` in `.env` instead of yaml.
4. Rebuild and restart:
   ```bash
   docker compose build mentor-core && docker compose up -d mentor-core
   ```

### Outreach modes

| Mode | Behavior |
|------|----------|
| `notify` | Telegram alert with listing summary + URL |
| `draft` | Alert + LLM-polished inquiry email body (default) |
| `email` | Send via SMTP when broker email found in listing; otherwise draft + link |

### Telegram

| Command | Description |
|---------|-------------|
| `/streeteasy` | Status: enabled, areas, last poll stats, listing counts |
| `/streeteasy poll` | Run one poll immediately |

New matches also create a **plan** tagged `apartment` / `streeteasy`.

### SMTP (optional, for `email` mode)

Set in `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

### Trigger events

New listings emit `listing.new` (entity = listing id). Add rules in `triggers.yaml` if you want extra reactions.

---

## Extending the system

### Add a trigger rule (no Python)

Edit `app/config/triggers.yaml`:

```yaml
  - match: { kind: location.enter, entity: library }
    reaction: notify
    message: "Study block — phone on focus mode?"
```

Restart `mentor-core`.

### Add a new adapter (Python)

1. Create `app/triggers/adapters/my_adapter.py`
2. Build `TriggerEvent` and call `get_router_instance().handle(event)`
3. Register route in `main.py` or run background task
4. Add matching rules in `triggers.yaml`

### Add a new reaction

1. Implement async function in `app/triggers/reactions.py`
2. Register in `main.py`: `trigger_router.register_reaction("my_reaction", my_func)`
3. Reference in YAML: `reaction: my_reaction`

---

## Quick reference card

```
# Memory
goal: ... | plan: ... | fact: ... | remember: ...
/add goal ... | /list | /show ID | /done ID | /status
/streeteasy | /streeteasy poll

# Reminders (timed)
"Remind me tomorrow at 9am to ..."

# Ops
docker compose up -d --build
docker logs -f mentor-core
curl http://127.0.0.1:8000/health

# HA
http://<TAILSCALE_IP>:8123
Webhook: POST 127.0.0.1:8000/webhooks/ha/location
```

---

## License and support

Private deployment; configure secrets locally. For changes to application code, edit under `app/` and rebuild the `mentor-core` image.
