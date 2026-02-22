# ㅤ𝑅𝑎𝑣𝑒𝑛 𝐺𝑟𝑜𝑢𝑝 ☻︎ — Distributed Multi-Bot Media Processing Platform

Production-grade Telegram multi-tenant bot system with dynamic clone management, premium access control, and high-throughput media processing. **No domain or file server required** — processed files are sent directly to users via Telegram.

---

## Architecture

```
Single Machine, Multi-Process (Railway VPS / any server)

┌─────────────────────────────────────────────────────┐
│                   FastAPI Process                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Mother Bot  │  │  Child Bot 1 │  │  Child N  │ │
│  │  (Admin)     │  │  (Public)    │  │  (Public) │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│         │                 │                 │        │
│         └─────────────────┴─────────────────┘        │
│                     Webhook Router                   │
│                  /webhook/{token}                    │
└─────────────────────────────────────────────────────┘
         │                    │
┌────────▼────────┐  ┌────────▼────────┐
│   Worker Pool   │  │    Scheduler    │
│  (8-100 slots)  │  │  (Background)   │
│  Priority Queue │  │  TTL Cleanup    │
│  Media Process  │  │  Disk Monitor   │
└────────┬────────┘  └─────────────────┘
         │
┌────────▼────────────────────────────────────────────┐
│              Shared Infrastructure                   │
│   Redis (Queue, Cache, Sessions)                    │
│   Database (SQLite/PostgreSQL)                      │
│   Temp Storage (/tmp/raven_media)                   │
└─────────────────────────────────────────────────────┘
```

---

## Features

### Bot System
- **Mother Bot** — Hidden admin control layer, never processes media
- **Child Bots** — Public-facing, dynamically cloned, hot-loaded without restart
- **Webhook Mode** — No polling, pure webhook delivery
- **Dynamic Token Loading** — Add new bots via `/clone` with instant activation

### Access Control
- **Free Tier** — 10 credits/day, group only, 2 concurrent jobs, 30s cooldown
- **Premium Tier** — Unlimited, private + group, 5 concurrent jobs, priority queue
- **Group Authorization** — Per-bot group authorization via `/auth`
- **Ban/Unban** — Admin-controlled user banning

### Media Processing
- Direct public media URLs only
- Blocked: YouTube, Facebook, Instagram, Twitter/X, Reddit, TikTok, and more
- Pipeline: Detect → Extract → Download → Optimize (ffmpeg) → **Send directly via Telegram**
- 20-block live progress bar, updates every 5 seconds
- **No domain required** — files are uploaded directly to Telegram and sent to the user
- Temp files are automatically deleted after sending
- Supports video (mp4, mkv, avi, mov, webm), audio (mp3, aac, ogg, flac, wav), and documents

### Premium System
- Key generation with configurable duration
- Key redemption via `/redeem`
- Automatic expiry tracking
- Premium extends existing subscription

### Emoji System
- Dynamic emoji pack ingestion
- Per-role emoji assignment via `/assign`
- Multi-pack randomization
- Fallback to Unicode defaults

### Broadcast
- Cross-clone broadcast to all users
- Authorized group broadcast
- Rate-limited batch sending (anti-ban)

---

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo>
cd raven-platform
cp .env.example .env
# Edit .env with your values
```

### 2. Required Environment Variables

```env
BOT_TOKEN=your_mother_bot_token
OWNER_ID=your_telegram_user_id
ADMIN_IDS=your_id,other_admin_id
REDIS_URL=redis://localhost:6379
DATABASE_URL=sqlite+aiosqlite:///./raven.db
BASE_URL=https://your-domain.com   # Used for webhook registration only
PORT=8000
```

> **Note:** `BASE_URL` is only needed for Telegram webhook registration. No file serving endpoint is exposed — all media is delivered directly through Telegram's API.

### 3. Run Locally

```bash
pip install -r requirements.txt
python main.py
```

### 4. Deploy to Railway

1. Create a new Railway project
2. Add a Redis service
3. Set all environment variables from `.env.example`
4. Set `BASE_URL` to your Railway public URL (for webhook registration)
5. Deploy — Railway auto-detects the `Dockerfile`

---

## Bot Commands

### Mother Bot (Admin Only)

| Command | Description |
|---------|-------------|
| `/clone <token>` | Request to add a new child bot |
| `/genkey [days]` | Generate a premium key (default: 30 days) |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/broadcast <msg>` | Broadcast to all users and groups |
| `/stats` | System statistics |
| `/assign` | Assign emojis to roles |
| `/assigned` | View all assigned emojis |
| `/restart` | Graceful system restart |
| `/disable_bot <id>` | Disable a child bot |
| `/enable_bot <id>` | Enable a child bot |
| `/auth` | Authorize current group |

### All Bots (Public)

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Help information |
| `/status` | Your account status |
| `/redeem <key>` | Activate premium key |
| `/auth` | Authorize group (admin only) |

### Media Processing

Send any direct media URL to trigger processing:
```
https://example.com/video.mp4
```

---

## Clone System Flow

```
Admin: /clone <bot_token>
  ↓
Validate token format
  ↓
Call Telegram getMe API
  ↓
Store in pending registry (Redis, 1h TTL)
  ↓
Notify OWNER with [Approve] [Decline] buttons
  ↓
Owner clicks Approve
  ↓
Register child bot + webhook
  ↓
Bot is live instantly (no restart)
```

---

## Processing Pipeline

```
User sends URL
  ↓
🔎 Link detected
  ↓
📂 Extracting media…
  ↓
⬇️ Downloading…
   ████████████░░░░░░░░ 60%
  ↓
⚙️ Optimizing…
   ████████████████████ 100%
  ↓
✅ Ready — file sent directly to chat
   (video/audio/document via Telegram API)
  ↓
🗑️ Temp file deleted from server
```

---

## Scaling

| Config | Concurrent Jobs |
|--------|----------------|
| `WORKER_POOL_SIZE=8` | ~50 jobs |
| `WORKER_POOL_SIZE=16` | ~100 jobs |
| `WORKER_POOL_SIZE=32` | ~200 jobs |

Adjust `MAX_CONCURRENT_JOBS` accordingly.

---

## Database Schema

- **bots** — Registered bot tokens and status
- **users** — User profiles, premium expiry, download counts
- **premium_keys** — Generated keys and redemption tracking
- **authorized_groups** — Per-bot group authorization
- **download_logs** — Processing history

---

## File Structure

```
/app
  /api          — FastAPI app, webhook routing
  /config       — Settings and environment management
  /handlers     — Mother bot and child bot command handlers
  /scheduler    — Background maintenance tasks (file cleanup, disk monitor)
  /services     — Redis, database, emoji, user, premium services
  /ui           — Message templates, progress engine, keyboards
  /utils        — Fonts, security, helpers
  /workers      — Media processor (ffmpeg), worker pool, job models
Dockerfile
main.py
requirements.txt
.env.example
```

---

## Security

- Webhook secret token validation (optional)
- Admin IDs loaded from environment only (never hardcoded)
- Duplicate job detection per user
- No public file serving endpoint — files go directly through Telegram

---

## Health Check

```
GET /health
```

Returns:
```json
{
  "status": "ok",
  "redis": "connected",
  "bots": 3,
  "workers": {
    "active_jobs": 5,
    "high_queue_size": 0,
    "normal_queue_size": 2,
    "pool_size": 8,
    "running": true
  }
}
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Web server for webhook handling |
| `aiogram 3` | Telegram Bot API client |
| `sqlalchemy` + `aiosqlite` | Async database ORM (SQLite default) |
| `asyncpg` | PostgreSQL async driver (optional) |
| `redis` | Queue, cache, session storage |
| `httpx` | Async HTTP client for media download |
| `ffmpeg-python` | Media optimization wrapper |
| `aiofiles` | Async file I/O |
| `pydantic-settings` | Environment variable management |
