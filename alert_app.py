import os
import time as time_module
import logging
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, time, timezone
from dotenv import load_dotenv

# Load environment values from local .env for local runs.
# In GitHub Actions, runtime values are injected via repository secrets.
load_dotenv()

# ----------------------------- Config keys/macros -----------------------------
CFG_TELEGRAM_CHAT_ID = 'TELEGRAM_CHAT_ID'
CFG_TELEGRAM_BOT_TOKEN = 'TELEGRAM_BOT_TOKEN'
CFG_EMAIL_ADDRESS = 'EMAIL_ADDRESS'
CFG_EMAIL_PASSWORD = 'EMAIL_PASSWORD'

CFG_EXECUTION_START_TIME = 'EXECUTION_START_TIME'
CFG_EXECUTION_STOP_TIME = 'EXECUTION_STOP_TIME'
CFG_ALERT_WINDOW_START_TIME = 'ALERT_WINDOW_START_TIME'
CFG_ALERT_WINDOW_END_TIME = 'ALERT_WINDOW_END_TIME'
CFG_ALERT_INTERVAL_MINUTES = 'ALERT_INTERVAL_MINUTES'
CFG_MANUAL_TEST_MODE = 'MANUAL_TEST_MODE'
CFG_LOCAL_CONTINUOUS_MODE = 'LOCAL_CONTINUOUS_MODE'
CFG_LOCAL_LOOP_SLEEP_SECONDS = 'LOCAL_LOOP_SLEEP_SECONDS'

# Backward compatibility keys (hour-only values from previous version)
CFG_OLD_EXECUTION_START_HOUR = 'EXECUTION_START_HOUR'
CFG_OLD_EXECUTION_STOP_HOUR = 'EXECUTION_STOP_HOUR'
CFG_OLD_ALERT_START_HOUR = 'ALERT_START_HOUR'
CFG_OLD_ALERT_END_HOUR = 'ALERT_END_HOUR'
CFG_OLD_ALERT_INTERVAL_HOURS = 'ALERT_INTERVAL_HOURS'

# Defaults requested by user
DEFAULT_EXECUTION_START_TIME = '08:00'
DEFAULT_EXECUTION_STOP_TIME = '16:00'
DEFAULT_ALERT_WINDOW_START_TIME = '09:30'
DEFAULT_ALERT_WINDOW_END_TIME = '15:30'
DEFAULT_ALERT_INTERVAL_MINUTES = 60
DEFAULT_LOCAL_CONTINUOUS_MODE = False
DEFAULT_LOCAL_LOOP_SLEEP_SECONDS = 5

# Text templates (configurable words/macros)
CFG_STARTUP_SIGNAL_TEMPLATE = 'STARTUP_SIGNAL_TEMPLATE'
CFG_ALERT_MESSAGE_TEMPLATE = 'ALERT_MESSAGE_TEMPLATE'
CFG_SUMMARY_SUBJECT_TEMPLATE = 'SUMMARY_SUBJECT_TEMPLATE'
CFG_MANUAL_TEST_MESSAGE_TEMPLATE = 'MANUAL_TEST_MESSAGE_TEMPLATE'

DEFAULT_STARTUP_SIGNAL_TEMPLATE = (
    '✅ Alert app started at {timestamp} | execution window: {execution_start}-{execution_stop} | '
    'alert window: {alert_start}-{alert_end}'
)
DEFAULT_ALERT_MESSAGE_TEMPLATE = 'Alert at {timestamp}'
DEFAULT_SUMMARY_SUBJECT_TEMPLATE = 'Daily Alert Summary - {date}'
DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE = '🧪 Manual test signal at {timestamp} (window checks bypassed)'

# Logging and network settings
LOG_FILE_PATH = 'alert.log'
LOG_LEVEL = logging.INFO
TELEGRAM_API_URL_TEMPLATE = 'https://api.telegram.org/bot{token}/sendMessage'
HTTP_TIMEOUT_SECONDS = 15
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
TIME_FORMAT = '%H:%M'
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'


def _env(name, default=''):
    """Read an environment variable with a default fallback."""
    return os.environ.get(name, default)


def _to_bool(value):
    """Parse common truthy/falsey strings into a boolean."""
    normalized = str(value).strip().lower()
    return normalized in {'1', 'true', 'yes', 'y', 'on'}


def _to_time(value, var_name):
    """Parse HH:MM string into a time object with clear error context."""
    try:
        parsed = datetime.strptime(value, TIME_FORMAT)
        return parsed.time().replace(second=0, microsecond=0)
    except ValueError as exc:
        raise ValueError(f'{var_name} must be in HH:MM format (24-hour). Got: {value}') from exc


def _hour_to_time_from_old_env(old_key, fallback_time):
    old_raw = _env(old_key, '').strip()
    if not old_raw:
        return fallback_time
    try:
        hour_int = int(old_raw)
    except ValueError as exc:
        raise ValueError(f'{old_key} must be an integer hour (0-23). Got: {old_raw}') from exc
    if hour_int < 0 or hour_int > 23:
        raise ValueError(f'{old_key} must be between 0 and 23. Got: {hour_int}')
    return time(hour=hour_int, minute=0)


def _load_config():
    """Load all runtime config values from environment (or defaults)."""
    execution_start = _to_time(
        _env(CFG_EXECUTION_START_TIME, DEFAULT_EXECUTION_START_TIME),
        CFG_EXECUTION_START_TIME,
    )
    execution_stop = _to_time(
        _env(CFG_EXECUTION_STOP_TIME, DEFAULT_EXECUTION_STOP_TIME),
        CFG_EXECUTION_STOP_TIME,
    )
    alert_start = _to_time(
        _env(CFG_ALERT_WINDOW_START_TIME, DEFAULT_ALERT_WINDOW_START_TIME),
        CFG_ALERT_WINDOW_START_TIME,
    )
    alert_end = _to_time(
        _env(CFG_ALERT_WINDOW_END_TIME, DEFAULT_ALERT_WINDOW_END_TIME),
        CFG_ALERT_WINDOW_END_TIME,
    )

    # Backward compatibility if old hour-only keys are set.
    if _env(CFG_OLD_EXECUTION_START_HOUR):
        execution_start = _hour_to_time_from_old_env(CFG_OLD_EXECUTION_START_HOUR, execution_start)
    if _env(CFG_OLD_EXECUTION_STOP_HOUR):
        execution_stop = _hour_to_time_from_old_env(CFG_OLD_EXECUTION_STOP_HOUR, execution_stop)
    if _env(CFG_OLD_ALERT_START_HOUR):
        alert_start = _hour_to_time_from_old_env(CFG_OLD_ALERT_START_HOUR, alert_start)
    if _env(CFG_OLD_ALERT_END_HOUR):
        alert_end = _hour_to_time_from_old_env(CFG_OLD_ALERT_END_HOUR, alert_end)

    interval_minutes_raw = _env(CFG_ALERT_INTERVAL_MINUTES, '').strip()
    if interval_minutes_raw:
        interval_minutes = int(interval_minutes_raw)
    else:
        old_interval_hours = _env(CFG_OLD_ALERT_INTERVAL_HOURS, '').strip()
        interval_minutes = int(old_interval_hours) * 60 if old_interval_hours else DEFAULT_ALERT_INTERVAL_MINUTES

    return {
        'telegram_chat_id': _env(CFG_TELEGRAM_CHAT_ID).strip(),
        'telegram_bot_token': _env(CFG_TELEGRAM_BOT_TOKEN).strip(),
        'email_address': _env(CFG_EMAIL_ADDRESS).strip(),
        'email_password': _env(CFG_EMAIL_PASSWORD).strip(),
        'execution_start': execution_start,
        'execution_stop': execution_stop,
        'alert_start': alert_start,
        'alert_end': alert_end,
        'interval_minutes': interval_minutes,
        'startup_template': _env(CFG_STARTUP_SIGNAL_TEMPLATE, DEFAULT_STARTUP_SIGNAL_TEMPLATE),
        'alert_template': _env(CFG_ALERT_MESSAGE_TEMPLATE, DEFAULT_ALERT_MESSAGE_TEMPLATE),
        'summary_subject_template': _env(CFG_SUMMARY_SUBJECT_TEMPLATE, DEFAULT_SUMMARY_SUBJECT_TEMPLATE),
        'manual_test_mode': _to_bool(_env(CFG_MANUAL_TEST_MODE, 'false')),
        'manual_test_template': _env(CFG_MANUAL_TEST_MESSAGE_TEMPLATE, DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE),
        'local_continuous_mode': _to_bool(_env(CFG_LOCAL_CONTINUOUS_MODE, str(DEFAULT_LOCAL_CONTINUOUS_MODE))),
        'local_loop_sleep_seconds': int(_env(CFG_LOCAL_LOOP_SLEEP_SECONDS, str(DEFAULT_LOCAL_LOOP_SLEEP_SECONDS))),
    }


def _minutes_since_midnight(value_time):
    return (value_time.hour * 60) + value_time.minute


def _validate_config(config):
    """Validate required values and chronological windows before processing."""
    missing = []
    if not config['telegram_chat_id']:
        missing.append(CFG_TELEGRAM_CHAT_ID)
    if not config['telegram_bot_token']:
        missing.append(CFG_TELEGRAM_BOT_TOKEN)
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    if config['interval_minutes'] <= 0:
        raise ValueError(f'{CFG_ALERT_INTERVAL_MINUTES} must be greater than 0')

    if config['local_loop_sleep_seconds'] <= 0:
        raise ValueError(f'{CFG_LOCAL_LOOP_SLEEP_SECONDS} must be greater than 0')

    execution_start_min = _minutes_since_midnight(config['execution_start'])
    execution_stop_min = _minutes_since_midnight(config['execution_stop'])
    alert_start_min = _minutes_since_midnight(config['alert_start'])
    alert_end_min = _minutes_since_midnight(config['alert_end'])

    if not (execution_start_min < alert_start_min <= alert_end_min < execution_stop_min):
        raise ValueError(
            f'Expected {CFG_EXECUTION_START_TIME} < {CFG_ALERT_WINDOW_START_TIME} <= '
            f'{CFG_ALERT_WINDOW_END_TIME} < {CFG_EXECUTION_STOP_TIME}'
        )


logging.basicConfig(filename=LOG_FILE_PATH, level=LOG_LEVEL)


def send_telegram_alert(config, message):
    """Send a Telegram message and log API/network failures without crashing the run."""
    api_url = TELEGRAM_API_URL_TEMPLATE.format(token=config['telegram_bot_token'])
    payload = {'chat_id': config['telegram_chat_id'], 'text': message}

    try:
        response = requests.post(api_url, data=payload, timeout=HTTP_TIMEOUT_SECONDS)
        if not response.ok:
            logging.error('Telegram send failed. status=%s body=%s', response.status_code, response.text)
            return False
        return True
    except requests.RequestException as exc:
        logging.exception('Telegram send raised exception: %s', exc)
        return False


def send_daily_summary(config, log_messages, run_date):
    """Send email summary if email credentials exist; otherwise skip silently with log."""
    if not config['email_address'] or not config['email_password']:
        logging.info('Email credentials not configured; skipping daily summary email.')
        return

    summary_subject = config['summary_subject_template'].format(date=run_date.isoformat())
    message_body = '\n'.join(log_messages) if log_messages else 'No alert slots configured for today.'

    msg = MIMEText(message_body)
    msg['Subject'] = summary_subject
    msg['From'] = config['email_address']
    msg['To'] = config['email_address']

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(config['email_address'], config['email_password'])
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        logging.exception('Daily summary email failed: %s', exc)


def _is_inclusive_window(current_time, start_time, end_time):
    return start_time <= current_time <= end_time


def _is_alert_slot(current_time, alert_start, interval_minutes):
    current_minutes = _minutes_since_midnight(current_time)
    alert_start_minutes = _minutes_since_midnight(alert_start)
    return (current_minutes - alert_start_minutes) % interval_minutes == 0


def _build_daily_summary(config, run_date):
    alert_start_minutes = _minutes_since_midnight(config['alert_start'])
    alert_end_minutes = _minutes_since_midnight(config['alert_end'])
    interval = config['interval_minutes']

    summary_slots = []
    current = alert_start_minutes
    while current <= alert_end_minutes:
        hour = current // 60
        minute = current % 60
        summary_slots.append(f'{run_date.isoformat()} {hour:02d}:{minute:02d}')
        current += interval

    return summary_slots


def _process_scheduled_logic(config, now):
    """Process one UTC timestamp and execute at most one action."""
    now_time = now.time()

    execution_start = config['execution_start']
    execution_stop = config['execution_stop']
    alert_start = config['alert_start']
    alert_end = config['alert_end']

    if not _is_inclusive_window(now_time, execution_start, execution_stop):
        logging.info('Outside execution window; no action taken.')
        return

    if now_time == execution_start:
        startup_message = config['startup_template'].format(
            timestamp=now.strftime(TIMESTAMP_FORMAT),
            execution_start=execution_start.strftime(TIME_FORMAT),
            execution_stop=execution_stop.strftime(TIME_FORMAT),
            alert_start=alert_start.strftime(TIME_FORMAT),
            alert_end=alert_end.strftime(TIME_FORMAT),
        )
        send_telegram_alert(config, startup_message)
        logging.info('Startup signal processed.')
        return

    if now_time == execution_stop:
        summary_messages = _build_daily_summary(config, now.date())
        logging.info('Execution stop time reached; sending daily summary if configured.')
        send_daily_summary(config, summary_messages, now.date())
        return

    if _is_inclusive_window(now_time, alert_start, alert_end) and _is_alert_slot(
        now_time,
        alert_start,
        config['interval_minutes'],
    ):
        alert_message = config['alert_template'].format(timestamp=now.strftime(TIMESTAMP_FORMAT))
        send_telegram_alert(config, alert_message)
        logging.info('Alert slot processed.')
        return

    logging.info('Inside execution window, but not a startup/summary/alert slot.')


def _run_local_continuous_mode(config):
    """Local runner: evaluates schedule continuously without changing GitHub behavior."""
    logging.info('Local continuous mode enabled. Watching schedule in UTC every %s second(s).', config['local_loop_sleep_seconds'])
    last_processed_minute = None

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        if now != last_processed_minute:
            _process_scheduled_logic(config, now)
            last_processed_minute = now

        time_module.sleep(config['local_loop_sleep_seconds'])


def main():
    """One-shot run for scheduled CI execution.

    The job is expected to run on the configured cron schedule. Based on current UTC time,
    this function decides whether to send startup signal, alert, summary, or no-op.
    """
    config = _load_config()
    _validate_config(config)

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    execution_start = config['execution_start']
    execution_stop = config['execution_stop']
    alert_start = config['alert_start']
    alert_end = config['alert_end']

    if config['manual_test_mode']:
        manual_test_message = config['manual_test_template'].format(
            timestamp=now.strftime(TIMESTAMP_FORMAT),
        )
        send_telegram_alert(config, manual_test_message)
        logging.info('Manual test mode processed.')
        return

    if config['local_continuous_mode']:
        _run_local_continuous_mode(config)
        return

    _process_scheduled_logic(config, now)

if __name__ == '__main__':
    main()


