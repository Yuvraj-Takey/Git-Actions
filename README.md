# GitHub Actions – Alert Bot Demo

A simple Python application that sends a startup Telegram signal, sends Telegram alerts in a configured alert window, and can email a daily summary. The app is designed as a GitHub Actions demo using a scheduled workflow, which is the correct approach for CI/CD jobs that should run and exit.

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
| `EXECUTION_START_TIME` | Optional | `08:00` | App execution start time (HH:MM, UTC); startup signal is sent here |
| `EXECUTION_STOP_TIME` | Optional | `16:00` | App execution stop time (HH:MM, UTC); daily summary can be sent here |
| `ALERT_WINDOW_START_TIME` | Optional | `09:30` | Alert window start (HH:MM, UTC) |
| `ALERT_WINDOW_END_TIME` | Optional | `15:30` | Alert window end (HH:MM, UTC) |
| `ALERT_INTERVAL_MINUTES` | Optional | `60` | Alert interval in minutes |
| `STARTUP_SIGNAL_TEMPLATE` | Optional | built-in default | Startup message template (`{timestamp}`, `{execution_start}`, `{execution_stop}`, `{alert_start}`, `{alert_end}`) |
| `ALERT_MESSAGE_TEMPLATE` | Optional | built-in default | Alert message template (`{timestamp}`) |
| `SUMMARY_SUBJECT_TEMPLATE` | Optional | built-in default | Email summary subject template (`{date}`) |
| `MANUAL_TEST_MODE` | Optional | `false` | When `true`, sends immediate test Telegram signal and exits |
| `MANUAL_TEST_MESSAGE_TEMPLATE` | Optional | built-in default | Manual test message template (`{timestamp}`) |

At runtime the app decides whether the current scheduled run is an alert slot or the end-of-day summary slot.

---

## 🚀 Setup & Deployment

## ✅ First Run Checklist (5 minutes)

1. Copy [.env.example](github_actions/.env.example) to [.env](github_actions/.env).
2. Fill `.env` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Keep email values empty if you do not want daily email yet.
4. Commit and push everything **except** `.env`.
5. In GitHub, add repository secrets (same key names as in `.env`).
6. Run the workflow once from **Actions → Deploy Python Application → Run workflow**.
7. Confirm the run logs and check Telegram for the startup signal.

For immediate manual testing, run workflow with `manual_test_mode=true` in the workflow dispatch form.

---

## 🧠 Terminology (important)

- **Execution window** = when GitHub Actions starts this job from cron in [github_actions/.github/workflows/deploy.yml](github_actions/.github/workflows/deploy.yml) and when the app accepts processing (`EXECUTION_START_TIME` to `EXECUTION_STOP_TIME`).
- **Alert window** = app logic (`ALERT_WINDOW_START_TIME` to `ALERT_WINDOW_END_TIME`) inside [github_actions/alert_app.py](github_actions/alert_app.py).

These can be different; best practice is to keep them aligned.

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
    | `MANUAL_TEST_MODE` | `true` / `false` |
    | `MANUAL_TEST_MESSAGE_TEMPLATE` | optional message template |

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

Behavior by hour (default setup):
- `08:00` → sends startup Telegram signal.
- `09:30` to `15:30` → sends alert(s) based on `ALERT_INTERVAL_MINUTES`.
- `16:00` → sends daily summary email (if email creds exist).

Default cron timing is configured as:
- `0 8 * * *` (startup)
- `30 9-15 * * *` (hourly alerts at `:30`)
- `0 16 * * *` (summary)

---

## 🪲 Debugging

- **Missing secrets error** – The app prints clearly which environment variable is missing at startup.
- **Telegram not working** – Test your bot token/chat ID with: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
- **Logs** – Alerts are logged to `alert.log` (excluded from Git by `.gitignore`).
- **GitHub Actions logs** – Go to repo → **Actions** tab → click a workflow run → expand each step.
- **Daily summary** – At the end hour, the app creates a summary from the configured alert schedule and sends it by email when email secrets are provided.
