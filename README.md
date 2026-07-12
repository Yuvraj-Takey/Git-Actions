# GitHub Actions – Alert Bot Demo

A simple Python application that sends Telegram alerts only during configured market hours. It is designed for GitHub Actions scheduled runs, with frequent triggers and in-app slot matching for high reliability.

---

## 📁 Folder Structure

```
github_actions/
├── alert_app.py                  # Main application
├── requirements.txt              # Python dependencies
├── .env.example                  # Template – safe to commit
├── .env                          # Your local credentials – NEVER commit this
├── .gitignore                    # Excludes .env, logs, and state from Git
└── .github/
    └── workflows/
        └── deploy.yml            # GitHub Actions workflow
```

---

## 🔐 Security – No Credentials in Code

All sensitive values (bot token, chat ID, email password) are stored **outside the code** using two mechanisms:

| Where | How |
|---|---|
| **Local machine** | `.env` file (loaded by `python-dotenv`, excluded from Git via `.gitignore`) |
| **GitHub Actions** | GitHub repository Secrets (injected as environment variables at runtime) |

> ✅ `.env` is in `.gitignore` so it can never be accidentally pushed.
> ✅ `.env.example` is the committed template – it has no real values.

---

## ⚙️ Configuration Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ Yes | — | Your Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ Yes | — | Your Telegram chat/group ID |
| `EMAIL_ADDRESS` | Optional | — | Gmail address for daily summary |
| `EMAIL_PASSWORD` | Optional | — | Gmail App Password (not your login password) |
| `EXECUTION_START_TIME` | Optional | `09:00` | App execution start time (HH:MM, **in DISPLAY_TIMEZONE**) |
| `EXECUTION_STOP_TIME` | Optional | `15:30` | App execution stop time (HH:MM, **in DISPLAY_TIMEZONE**) |
| `ALERT_WINDOW_START_TIME` | Optional | `09:00` | Alert window start (HH:MM, **in DISPLAY_TIMEZONE**) |
| `ALERT_WINDOW_END_TIME` | Optional | `15:30` | Alert window end (HH:MM, **in DISPLAY_TIMEZONE**) |
| `ALERT_INTERVAL_MINUTES` | Optional | `60` | Alert interval in minutes |
| `STARTUP_SIGNAL_TEMPLATE` | Optional | built-in default | Kept for backward compatibility; not used in market-alert-only scheduled mode |
| `ALERT_MESSAGE_TEMPLATE` | Optional | built-in default | Alert message template (`{timestamp}`) |
| `SUMMARY_SUBJECT_TEMPLATE` | Optional | built-in default | Kept for backward compatibility |
| `DISPLAY_TIMEZONE` | Optional | `Asia/Kolkata` | Timezone used in message timestamps (example: `Asia/Kolkata`) |
| `MANUAL_TEST_MODE` | Optional | `false` | When `true`, sends immediate test Telegram signal and exits |
| `MANUAL_TEST_MESSAGE_TEMPLATE` | Optional | built-in default | Manual test message template (`{timestamp}`) |
| `NOTIFY_ON_EACH_RUN_START` | Optional | `false` | When `true`, sends a Telegram message at the start of every run (can look like duplicate "run started" messages if runs happen outside alert slots) |
| `RUN_START_MESSAGE_TEMPLATE` | Optional | built-in default | Run-start message template (`{timestamp}`) |
| `SLOT_TOLERANCE_MINUTES` | Optional | `14` | Delay window in minutes for due alert slot matching |
| `MAX_CATCHUP_MINUTES` | Optional | `14` | Upper bound for delayed alert processing (use same value as `SLOT_TOLERANCE_MINUTES`) |
| `LOCAL_CONTINUOUS_MODE` | Optional | `false` | For local runs only: keep process alive and evaluate schedule continuously |
| `LOCAL_LOOP_SLEEP_SECONDS` | Optional | `5` | Local loop polling interval in seconds |

At runtime the app sends only due interval alerts inside market hours.

Template placeholders available in Telegram templates:
- `{timestamp}` (same as actual run time, backward compatible)
- `{actual_run_time}`
- `{scheduled_slot_time}`
- `{scheduled_slot_timestamp}`
- `{display_timezone}`

---

## 🚀 Setup & Deployment

## ✅ First Run Checklist (5 minutes)

1. Copy [.env.example](github_actions/.env.example) to [.env](github_actions/.env).
2. Fill `.env` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Keep email values empty if you do not want daily email yet.
4. Commit and push everything **except** `.env`.
5. In GitHub, add repository secrets (same key names as in `.env`).
6. Run the workflow once from **Actions → Deploy Python Application → Run workflow**.
7. Confirm the run logs and check Telegram for market-hour alerts.

For immediate manual testing, run workflow with `manual_test_mode=true` in the workflow dispatch form.

For local continuous testing, set `LOCAL_CONTINUOUS_MODE=true` in [.env](github_actions/.env), then run [github_actions/alert_app.py](github_actions/alert_app.py). Stop with `Ctrl+C`.

---

## 🧠 Terminology (important)

- **Time windows** = All configured times (`EXECUTION_START_TIME`, `EXECUTION_STOP_TIME`, `ALERT_WINDOW_START_TIME`, `ALERT_WINDOW_END_TIME`) are interpreted in `DISPLAY_TIMEZONE` (default `Asia/Kolkata` = IST). Set times as IST directly — no UTC conversion needed.
- **Execution window** = when the app accepts processing (`EXECUTION_START_TIME` to `EXECUTION_STOP_TIME`).
- **Alert window** = app logic (`ALERT_WINDOW_START_TIME` to `ALERT_WINDOW_END_TIME`) inside [github_actions/alert_app.py](github_actions/alert_app.py).
- **Cron schedule** = defined in [github_actions/.github/workflows/deploy.yml](github_actions/.github/workflows/deploy.yml) in **UTC**. Must be kept in sync with your window times converted to UTC.

> ⚠️ If you change `DISPLAY_TIMEZONE`, also update the cron schedule in `deploy.yml` to match.

| IST time | UTC equivalent | Cron entry | Purpose |
|---|---|---|---|
| 08:00 AM | 02:30 AM | `30 2 * * *` | Startup signal |
| 09:30–15:30 hourly | 04:00–10:00 hourly | `0 4-10 * * *` | Hourly alerts |
| 04:00 PM | 10:30 AM | `30 10 * * *` | Daily summary |

---

### Step 1 – Clone & configure locally

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd github_actions
cp .env.example .env       # Copy the template
# Now edit .env with your real credentials
```

### Step 2 – Install dependencies locally (optional test)

```bash
pip install -r requirements.txt
python alert_app.py
```

The app runs once per execution, which makes it suitable for GitHub Actions schedules.

---

## 🔑 Adding GitHub Secrets (for CI/CD)

GitHub Actions reads credentials from **Secrets**, not from `.env`.

1. Go to your GitHub repository.
2. Click **Settings** → **Secrets and variables** → **Actions**.
3. Click **New repository secret** for each variable:

   | Secret Name | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | your bot token |
   | `TELEGRAM_CHAT_ID` | your chat ID |
   | `EMAIL_ADDRESS` | your email (optional) |
   | `EMAIL_PASSWORD` | your Gmail App Password (optional) |
    | `EXECUTION_START_TIME` | e.g. `08:00` |
    | `EXECUTION_STOP_TIME` | e.g. `16:00` |
    | `ALERT_WINDOW_START_TIME` | e.g. `09:30` |
    | `ALERT_WINDOW_END_TIME` | e.g. `15:30` |
    | `ALERT_INTERVAL_MINUTES` | e.g. `60` |
    | `STARTUP_SIGNAL_TEMPLATE` | optional message template |
    | `ALERT_MESSAGE_TEMPLATE` | optional message template |
    | `SUMMARY_SUBJECT_TEMPLATE` | optional message template |
    | `DISPLAY_TIMEZONE` | e.g. `Asia/Kolkata` |
    | `MANUAL_TEST_MODE` | `true` / `false` |
    | `MANUAL_TEST_MESSAGE_TEMPLATE` | optional message template |
    | `NOTIFY_ON_EACH_RUN_START` | `true` / `false` |
    | `RUN_START_MESSAGE_TEMPLATE` | optional message template |
    | `SLOT_TOLERANCE_MINUTES` | e.g. `10` |
    | `MAX_CATCHUP_MINUTES` | e.g. `75` |
    | `LOCAL_CONTINUOUS_MODE` | `true` / `false` (local only) |
    | `LOCAL_LOOP_SLEEP_SECONDS` | polling seconds (local only) |

> 💡 For Gmail, use an **App Password** (not your account password):
> Google Account → Security → 2-Step Verification → App passwords.

---

## 🤖 GitHub Actions Workflow

The workflow in `.github/workflows/deploy.yml` runs on a schedule and also supports manual execution:

1. Checks out the code.
2. Sets up Python.
3. Installs dependencies.
4. Runs `alert_app.py` once with all secrets injected as environment variables.

Manual execution supports a one-click input named `manual_test_mode`. When set to `true`, the app bypasses time-window checks and sends an immediate test Telegram message.

The scheduled demo uses cron entries so GitHub Actions starts the job only at required times (UTC), and each run exits cleanly.

Behavior by time (default IST setup):
- `09:00 AM to 03:30 PM IST` → interval alerts based on `ALERT_INTERVAL_MINUTES`.
- No startup ping and no after-hours scheduled alert sends.

Default cron timing is configured as IST-equivalent UTC, every 15 minutes on weekdays within market window:
- `30,45 3 * * 1-5` (UTC)
- `*/15 4-9 * * 1-5` (UTC)
- `0 10 * * 1-5` (UTC)

---

## 🪲 Debugging

- **Missing secrets error** – The app prints clearly which environment variable is missing at startup.
- **Telegram not working** – Test your bot token/chat ID with: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
- **Logs** – Alerts are logged to `alert.log` (excluded from Git by `.gitignore`).
- **GitHub Actions logs** – Go to repo → **Actions** tab → click a workflow run → expand each step.
- **Downloaded app log** – In the same run page, download artifact named `alert-log`.
- **No message sent** – If a run is outside market window or no slot is due yet, app logs a no-op line and exits.


