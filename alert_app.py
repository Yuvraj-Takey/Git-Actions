import os
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv  # Loads local .env when running from laptop/dev machine.

# ------------------------------------------------------------
# 1) Environment bootstrap
# ------------------------------------------------------------
# In GitHub Actions, environment variables are injected by workflow `env:`.
# For local testing, `.env` is loaded so the same code works without changes.
load_dotenv()


# ------------------------------------------------------------
# 2) Config keys (names used in environment variables)
# ------------------------------------------------------------
CFG_TELEGRAM_CHAT_ID = 'TELEGRAM_CHAT_ID'
CFG_TELEGRAM_BOT_TOKEN = 'TELEGRAM_BOT_TOKEN'
CFG_DISPLAY_TIMEZONE = 'DISPLAY_TIMEZONE'
CFG_MANUAL_TEST_MODE = 'MANUAL_TEST_MODE'
CFG_ALERT_MESSAGE_TEMPLATE = 'ALERT_MESSAGE_TEMPLATE'
CFG_MANUAL_TEST_MESSAGE_TEMPLATE = 'MANUAL_TEST_MESSAGE_TEMPLATE'


# ------------------------------------------------------------
# 3) Default values (used only when env var is missing)
# ------------------------------------------------------------
DEFAULT_DISPLAY_TIMEZONE = 'Asia/Kolkata'
DEFAULT_ALERT_MESSAGE_TEMPLATE = '📈 Market ping at {actual_run_time} ({display_timezone})'
DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE = '🧪 Manual test ping at {actual_run_time} ({display_timezone})'


# ------------------------------------------------------------
# 4) Runtime constants
# ------------------------------------------------------------
LOG_FILE_PATH = 'alert.log'
HTTP_TIMEOUT_SECONDS = 15
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'


# ------------------------------------------------------------
# 5) Logging setup
# ------------------------------------------------------------
# Logs go to both console (visible in GitHub Actions) and file (artifact upload).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)


def _env(name, default=''):
    """Read an environment variable with optional fallback."""
    return os.environ.get(name, default)


def _required_env(name):
    """Read a required variable and fail fast with a clear error message."""
    value = _env(name, '').strip()
    if not value:
        raise EnvironmentError(f'Missing required environment variable: {name}')
    return value


def _to_bool(value):
    """Convert common text flags to boolean (e.g., 'true', '1', 'yes')."""
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _load_config():
    """Build a minimal config dict for lightweight one-shot sending."""
    return {
        # Required Telegram identity.
        'telegram_chat_id': _required_env(CFG_TELEGRAM_CHAT_ID),
        'telegram_bot_token': _required_env(CFG_TELEGRAM_BOT_TOKEN),

        # Optional execution settings.
        'display_timezone': _env(CFG_DISPLAY_TIMEZONE, DEFAULT_DISPLAY_TIMEZONE).strip() or DEFAULT_DISPLAY_TIMEZONE,
        'manual_test_mode': _to_bool(_env(CFG_MANUAL_TEST_MODE, 'false')),

        # Optional templates.
        'alert_template': _env(CFG_ALERT_MESSAGE_TEMPLATE, DEFAULT_ALERT_MESSAGE_TEMPLATE),
        'manual_test_template': _env(CFG_MANUAL_TEST_MESSAGE_TEMPLATE, DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE),
    }


def _display_datetime(now_utc, config):
    """Convert UTC datetime to configured display timezone."""
    return now_utc.astimezone(ZoneInfo(config['display_timezone']))


def _build_message_context(now_utc, config):
    """Create template placeholders used in outgoing Telegram message."""
    now_local = _display_datetime(now_utc, config)
    return {
        # Backward-compatible alias.
        'timestamp': now_local.strftime(TIMESTAMP_FORMAT),

        # Preferred explicit field names.
        'actual_run_time': now_local.strftime(TIMESTAMP_FORMAT),
        'display_timezone': config['display_timezone'],
    }


def send_telegram_alert(config, message):
    """Send one Telegram message. Returns True on success, False otherwise."""
    # Telegram Bot API endpoint: /sendMessage
    api_url = f"https://api.telegram.org/bot{config['telegram_bot_token']}/sendMessage"
    payload = {
        'chat_id': config['telegram_chat_id'],
        'text': message,
    }

    try:
        response = requests.post(api_url, data=payload, timeout=HTTP_TIMEOUT_SECONDS)
        if not response.ok:
            logging.error('Telegram send failed. status=%s body=%s', response.status_code, response.text)
            return False
        return True
    except requests.RequestException as exc:
        logging.exception('Telegram send raised exception: %s', exc)
        return False


def main():
    """Main flow: load config -> build message -> send once -> exit."""
    # Step 1: Read and validate runtime inputs.
    config = _load_config()

    # Step 2: Validate timezone key early for cleaner failure messages.
    ZoneInfo(config['display_timezone'])

    # Step 3: Build current timestamp context in configured timezone.
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    context = _build_message_context(now_utc, config)

    # Step 4: Pick message template by mode.
    # - manual_test_mode=true  => sends test template
    # - manual_test_mode=false => sends normal market ping template
    if config['manual_test_mode']:
        message = config['manual_test_template'].format(**context)
    else:
        message = config['alert_template'].format(**context)

    # Step 5: Send message and fail run if delivery failed.
    sent = send_telegram_alert(config, message)
    if not sent:
        raise RuntimeError('Telegram message was not delivered. Check logs for API error details.')

    # Step 6: Final success log for run traceability.
    logging.info('Message sent successfully. manual_test_mode=%s', config['manual_test_mode'])


# Standard Python entrypoint.
if __name__ == '__main__':
    main()


