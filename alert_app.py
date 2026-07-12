import os  # Access environment variables like TELEGRAM_BOT_TOKEN, EXECUTION_START_TIME, etc.
import time as time_module  # Use sleep() for local continuous mode loop.
import logging  # Write runtime logs to file + console for debugging.
import requests  # Send Telegram HTTP requests.
import smtplib  # Send summary email via SMTP.
from email.mime.text import MIMEText  # Build plain-text email body safely.
from datetime import datetime, time, timezone  # Parse time values and generate UTC timestamps.
from zoneinfo import ZoneInfo  # Convert UTC -> configured display timezone (for IST handling).
from dotenv import load_dotenv  # Load .env during local runs.

# Load environment values from local .env for local runs.
# In GitHub Actions, runtime values are injected via repository secrets.
load_dotenv()

# ----------------------------- Config keys/macros -----------------------------
# Required Telegram variables.
CFG_TELEGRAM_CHAT_ID = 'TELEGRAM_CHAT_ID'
CFG_TELEGRAM_BOT_TOKEN = 'TELEGRAM_BOT_TOKEN'
# Optional email variables for daily summary.
CFG_EMAIL_ADDRESS = 'EMAIL_ADDRESS'
CFG_EMAIL_PASSWORD = 'EMAIL_PASSWORD'

# Core schedule variables.
CFG_EXECUTION_START_TIME = 'EXECUTION_START_TIME'
CFG_EXECUTION_STOP_TIME = 'EXECUTION_STOP_TIME'
CFG_ALERT_WINDOW_START_TIME = 'ALERT_WINDOW_START_TIME'
CFG_ALERT_WINDOW_END_TIME = 'ALERT_WINDOW_END_TIME'
CFG_ALERT_INTERVAL_MINUTES = 'ALERT_INTERVAL_MINUTES'
# Runtime behavior toggles.
CFG_MANUAL_TEST_MODE = 'MANUAL_TEST_MODE'
CFG_LOCAL_CONTINUOUS_MODE = 'LOCAL_CONTINUOUS_MODE'
CFG_LOCAL_LOOP_SLEEP_SECONDS = 'LOCAL_LOOP_SLEEP_SECONDS'
CFG_DISPLAY_TIMEZONE = 'DISPLAY_TIMEZONE'
CFG_SLOT_TOLERANCE_MINUTES = 'SLOT_TOLERANCE_MINUTES'
CFG_MAX_CATCHUP_MINUTES = 'MAX_CATCHUP_MINUTES'

# Backward compatibility keys (hour-only values from previous version).
CFG_OLD_EXECUTION_START_HOUR = 'EXECUTION_START_HOUR'
CFG_OLD_EXECUTION_STOP_HOUR = 'EXECUTION_STOP_HOUR'
CFG_OLD_ALERT_START_HOUR = 'ALERT_START_HOUR'
CFG_OLD_ALERT_END_HOUR = 'ALERT_END_HOUR'
CFG_OLD_ALERT_INTERVAL_HOURS = 'ALERT_INTERVAL_HOURS'

# Defaults used when env vars are not provided.
DEFAULT_LOCAL_CONTINUOUS_MODE = False
DEFAULT_LOCAL_LOOP_SLEEP_SECONDS = 5
DEFAULT_MAX_CATCHUP_MINUTES = 75

# Text template config keys.
CFG_STARTUP_SIGNAL_TEMPLATE = 'STARTUP_SIGNAL_TEMPLATE'
CFG_ALERT_MESSAGE_TEMPLATE = 'ALERT_MESSAGE_TEMPLATE'
CFG_SUMMARY_SUBJECT_TEMPLATE = 'SUMMARY_SUBJECT_TEMPLATE'
CFG_MANUAL_TEST_MESSAGE_TEMPLATE = 'MANUAL_TEST_MESSAGE_TEMPLATE'
CFG_NOTIFY_ON_EACH_RUN_START = 'NOTIFY_ON_EACH_RUN_START'
CFG_RUN_START_MESSAGE_TEMPLATE = 'RUN_START_MESSAGE_TEMPLATE'

# Default startup message (sent at execution start slot).
DEFAULT_STARTUP_SIGNAL_TEMPLATE = (
    '✅ Startup scheduled at {scheduled_slot_timestamp} | sent at {actual_run_time} | '
    'execution window: {execution_start}-{execution_stop} | alert window: {alert_start}-{alert_end}'
)
# Default alert message (sent for each alert slot).
DEFAULT_ALERT_MESSAGE_TEMPLATE = 'Alert scheduled at {scheduled_slot_timestamp} | sent at {actual_run_time}'
# Default email subject for daily summary.
DEFAULT_SUMMARY_SUBJECT_TEMPLATE = 'Daily Alert Summary - {date}'
# Default manual test message.
DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE = '🧪 Manual test signal at {timestamp} (window checks bypassed)'
# Whether to send “run started” on every run by default.
DEFAULT_NOTIFY_ON_EACH_RUN_START = False
# Default run-start message.
DEFAULT_RUN_START_MESSAGE_TEMPLATE = '🚀 Info: started Git-Actions at {timestamp}'

# Logging and network settings.
LOG_FILE_PATH = 'alert.log'  # Output log file name.
LOG_LEVEL = logging.INFO  # Log detail level.
TELEGRAM_API_URL_TEMPLATE = 'https://api.telegram.org/bot{token}/sendMessage'  # Telegram endpoint format.
HTTP_TIMEOUT_SECONDS = 15  # Request timeout for Telegram HTTP call.
SMTP_HOST = 'smtp.gmail.com'  # Gmail SMTP host.
SMTP_PORT = 587  # Gmail SMTP TLS port.
TIME_FORMAT = '%H:%M'  # Time-only format used for config and logs.
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'  # Full timestamp format used in messages.


def _env(name, default=''):
    """Read an environment variable with a default fallback."""
    return os.environ.get(name, default)  # Return env value, or fallback when missing.


def _required_env(name):
    """Read a required environment variable and fail with clear error if missing."""
    value = _env(name, '').strip()
    if not value:
        raise EnvironmentError(f'Missing required environment variable: {name}')
    return value


def _to_bool(value):
    """Parse common truthy/falsey strings into a boolean."""
    normalized = str(value).strip().lower()  # Normalize user text to compare safely.
    return normalized in {'1', 'true', 'yes', 'y', 'on'}  # Recognize common true tokens.


def _to_time(value, var_name):
    """Parse HH:MM string into a time object with clear error context."""
    try:
        parsed = datetime.strptime(value, TIME_FORMAT)  # Parse HH:MM string.
        return parsed.time().replace(second=0, microsecond=0)  # Keep minute precision only.
    except ValueError as exc:
        raise ValueError(f'{var_name} must be in HH:MM format (24-hour). Got: {value}') from exc


def _hour_to_time_from_old_env(old_key, fallback_time):
    """Convert legacy hour-only env values to HH:00 time."""
    old_raw = _env(old_key, '').strip()  # Read old env key value.
    if not old_raw:
        return fallback_time  # If old key is not set, keep already parsed new value.
    try:
        hour_int = int(old_raw)  # Parse integer hour.
    except ValueError as exc:
        raise ValueError(f'{old_key} must be an integer hour (0-23). Got: {old_raw}') from exc
    if hour_int < 0 or hour_int > 23:
        raise ValueError(f'{old_key} must be between 0 and 23. Got: {hour_int}')
    return time(hour=hour_int, minute=0)  # Convert to HH:00.


def _load_config():
    """Load all runtime config values from environment (or defaults)."""
    # Parse execution window start (HH:MM).
    execution_start = _to_time(
        _required_env(CFG_EXECUTION_START_TIME),
        CFG_EXECUTION_START_TIME,
    )
    # Parse execution window stop (HH:MM).
    execution_stop = _to_time(
        _required_env(CFG_EXECUTION_STOP_TIME),
        CFG_EXECUTION_STOP_TIME,
    )
    # Parse alert window start (HH:MM).
    alert_start = _to_time(
        _required_env(CFG_ALERT_WINDOW_START_TIME),
        CFG_ALERT_WINDOW_START_TIME,
    )
    # Parse alert window end (HH:MM).
    alert_end = _to_time(
        _required_env(CFG_ALERT_WINDOW_END_TIME),
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

    # Read interval in minutes from required key (or legacy hour key fallback).
    interval_minutes_raw = _env(CFG_ALERT_INTERVAL_MINUTES, '').strip()
    if interval_minutes_raw:
        try:
            interval_minutes = int(interval_minutes_raw)  # Use new minute-based config when present.
        except ValueError as exc:
            raise ValueError(f'{CFG_ALERT_INTERVAL_MINUTES} must be an integer. Got: {interval_minutes_raw}') from exc
    else:
        old_interval_hours = _env(CFG_OLD_ALERT_INTERVAL_HOURS, '').strip()  # Fallback old hours key.
        if old_interval_hours:
            try:
                interval_minutes = int(old_interval_hours) * 60
            except ValueError as exc:
                raise ValueError(f'{CFG_OLD_ALERT_INTERVAL_HOURS} must be an integer. Got: {old_interval_hours}') from exc
        else:
            raise EnvironmentError(
                f'Missing required environment variable: {CFG_ALERT_INTERVAL_MINUTES} '
                f'(or legacy {CFG_OLD_ALERT_INTERVAL_HOURS})'
            )

    slot_tolerance_raw = _required_env(CFG_SLOT_TOLERANCE_MINUTES)
    try:
        slot_tolerance_minutes = int(slot_tolerance_raw)
    except ValueError as exc:
        raise ValueError(f'{CFG_SLOT_TOLERANCE_MINUTES} must be an integer. Got: {slot_tolerance_raw}') from exc

    max_catchup_raw = _env(CFG_MAX_CATCHUP_MINUTES, str(DEFAULT_MAX_CATCHUP_MINUTES)).strip()
    try:
        max_catchup_minutes = int(max_catchup_raw)
    except ValueError as exc:
        raise ValueError(f'{CFG_MAX_CATCHUP_MINUTES} must be an integer. Got: {max_catchup_raw}') from exc

    # Build one normalized config object used by all runtime functions.
    return {
        'telegram_chat_id': _env(CFG_TELEGRAM_CHAT_ID).strip(),  # Telegram target chat.
        'telegram_bot_token': _env(CFG_TELEGRAM_BOT_TOKEN).strip(),  # Telegram bot token.
        'email_address': _env(CFG_EMAIL_ADDRESS).strip(),  # Summary sender/receiver email.
        'email_password': _env(CFG_EMAIL_PASSWORD).strip(),  # SMTP app password.
        'execution_start': execution_start,  # Start of execution window.
        'execution_stop': execution_stop,  # End of execution window.
        'alert_start': alert_start,  # Start of alert sub-window.
        'alert_end': alert_end,  # End of alert sub-window.
        'interval_minutes': interval_minutes,  # Alert gap in minutes.
        'startup_template': _env(CFG_STARTUP_SIGNAL_TEMPLATE, DEFAULT_STARTUP_SIGNAL_TEMPLATE),  # Startup text template.
        'alert_template': _env(CFG_ALERT_MESSAGE_TEMPLATE, DEFAULT_ALERT_MESSAGE_TEMPLATE),  # Alert text template.
        'summary_subject_template': _env(CFG_SUMMARY_SUBJECT_TEMPLATE, DEFAULT_SUMMARY_SUBJECT_TEMPLATE),  # Email subject template.
        'manual_test_mode': _to_bool(_env(CFG_MANUAL_TEST_MODE, 'false')),  # Manual test toggle.
        'manual_test_template': _env(CFG_MANUAL_TEST_MESSAGE_TEMPLATE, DEFAULT_MANUAL_TEST_MESSAGE_TEMPLATE),  # Manual test text.
        'notify_on_each_run_start': _to_bool(
            _env(CFG_NOTIFY_ON_EACH_RUN_START, str(DEFAULT_NOTIFY_ON_EACH_RUN_START))
        ),  # Run-start ping toggle.
        'run_start_template': _env(CFG_RUN_START_MESSAGE_TEMPLATE, DEFAULT_RUN_START_MESSAGE_TEMPLATE),  # Run-start text.
        'local_continuous_mode': _to_bool(_env(CFG_LOCAL_CONTINUOUS_MODE, str(DEFAULT_LOCAL_CONTINUOUS_MODE))),  # Local loop toggle.
        'local_loop_sleep_seconds': int(_env(CFG_LOCAL_LOOP_SLEEP_SECONDS, str(DEFAULT_LOCAL_LOOP_SLEEP_SECONDS))),  # Local loop sleep.
        'display_timezone': _required_env(CFG_DISPLAY_TIMEZONE),  # Display/compare timezone.
        'slot_tolerance_minutes': slot_tolerance_minutes,  # Tolerance for delayed scheduler runs.
        'max_catchup_minutes': max_catchup_minutes,  # Max delay (minutes) to still process missed slots.
    }


def _minutes_since_midnight(value_time):
    """Convert time object to total minutes from 00:00."""
    return (value_time.hour * 60) + value_time.minute  # Example: 09:30 -> 570.


def _validate_config(config):
    """Validate required values and chronological windows before processing."""
    missing = []  # Collect missing required env keys.
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

    if config['slot_tolerance_minutes'] < 0:
        raise ValueError(f'{CFG_SLOT_TOLERANCE_MINUTES} must be greater than or equal to 0')

    if config['max_catchup_minutes'] < 0:
        raise ValueError(f'{CFG_MAX_CATCHUP_MINUTES} must be greater than or equal to 0')

    try:
        ZoneInfo(config['display_timezone'])  # Validate timezone string.
    except Exception as exc:
        raise ValueError(f"Invalid {CFG_DISPLAY_TIMEZONE}: {config['display_timezone']}") from exc

    # Convert all schedule points to minutes for easy ordering validation.
    execution_start_min = _minutes_since_midnight(config['execution_start'])
    execution_stop_min = _minutes_since_midnight(config['execution_stop'])
    alert_start_min = _minutes_since_midnight(config['alert_start'])
    alert_end_min = _minutes_since_midnight(config['alert_end'])

    # Ensure alert window is fully inside execution window.
    if not (execution_start_min <= alert_start_min <= alert_end_min <= execution_stop_min):
        raise ValueError(
            f'Expected {CFG_EXECUTION_START_TIME} <= {CFG_ALERT_WINDOW_START_TIME} <= '
            f'{CFG_ALERT_WINDOW_END_TIME} <= {CFG_EXECUTION_STOP_TIME}'
        )


# Configure global logging once at import time.
logging.basicConfig(
    level=LOG_LEVEL,  # Logging severity level.
    format='%(asctime)s %(levelname)s %(message)s',  # Common log format.
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8'),  # Persist logs to alert.log.
        logging.StreamHandler(),  # Also print logs to console/GitHub Actions output.
    ],
)


def send_telegram_alert(config, message):
    """Send a Telegram message and log API/network failures without crashing the run."""
    api_url = TELEGRAM_API_URL_TEMPLATE.format(token=config['telegram_bot_token'])  # Resolve bot URL.
    payload = {'chat_id': config['telegram_chat_id'], 'text': message}  # Build telegram form payload.

    try:
        response = requests.post(api_url, data=payload, timeout=HTTP_TIMEOUT_SECONDS)  # Send message.
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

    summary_subject = config['summary_subject_template'].format(date=run_date.isoformat())  # Render subject.
    message_body = '\n'.join(log_messages) if log_messages else 'No alert slots configured for today.'  # Render body.

    msg = MIMEText(message_body)  # Build MIME email.
    msg['Subject'] = summary_subject  # Subject line.
    msg['From'] = config['email_address']  # Sender.
    msg['To'] = config['email_address']  # Receiver (self in this app).

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:  # Open SMTP connection.
            server.starttls()  # Upgrade to TLS.
            server.login(config['email_address'], config['email_password'])  # Authenticate.
            server.send_message(msg)  # Send message.
    except (smtplib.SMTPException, OSError) as exc:
        logging.exception('Daily summary email failed: %s', exc)


def _is_inclusive_window(current_time, start_time, end_time):
    """True when start <= current <= end."""
    return start_time <= current_time <= end_time


def _is_alert_slot(current_time, alert_start, interval_minutes):
    """Exact slot match helper (kept for compatibility/readability)."""
    current_minutes = _minutes_since_midnight(current_time)  # Convert current to minutes.
    alert_start_minutes = _minutes_since_midnight(alert_start)  # Convert start to minutes.
    return (current_minutes - alert_start_minutes) % interval_minutes == 0  # Exact modulus match.


def _is_exact_or_tolerant_match(current_time, target_time, tolerance_minutes):
    """True when current and target are equal or within tolerance."""
    current_minutes = _minutes_since_midnight(current_time)  # Current minute offset.
    target_minutes = _minutes_since_midnight(target_time)  # Target minute offset.
    return abs(current_minutes - target_minutes) <= tolerance_minutes  # Absolute distance check.


def _is_inclusive_window_with_tolerance(current_time, start_time, end_time, tolerance_minutes):
    """Window check expanded on both sides by tolerance minutes."""
    current_minutes = _minutes_since_midnight(current_time)  # Current minute offset.
    start_minutes = _minutes_since_midnight(start_time)  # Start minute offset.
    end_minutes = _minutes_since_midnight(end_time)  # End minute offset.
    return (start_minutes - tolerance_minutes) <= current_minutes <= (end_minutes + tolerance_minutes)


def _is_alert_slot_with_tolerance(current_time, alert_start, interval_minutes, tolerance_minutes):
    """Alert slot matcher that allows early/late scheduler jitter."""
    current_minutes = _minutes_since_midnight(current_time)  # Current minute offset.
    alert_start_minutes = _minutes_since_midnight(alert_start)  # Alert start offset.

    if current_minutes < (alert_start_minutes - tolerance_minutes):
        return False  # Too early to be considered a valid slot.

    remainder = (current_minutes - alert_start_minutes) % interval_minutes  # Distance from nearest slot.
    return remainder <= tolerance_minutes or (interval_minutes - remainder) <= tolerance_minutes


def _find_latest_slot_at_or_before(current_time, window_start, window_end, interval_minutes):
    """Return latest valid slot <= current_time within [window_start, window_end], else None."""
    current_minutes = _minutes_since_midnight(current_time)
    start_minutes = _minutes_since_midnight(window_start)
    end_minutes = _minutes_since_midnight(window_end)

    if current_minutes < start_minutes:
        return None

    bounded_current = min(current_minutes, end_minutes)
    elapsed = bounded_current - start_minutes
    steps = elapsed // interval_minutes
    slot_minutes = start_minutes + (steps * interval_minutes)

    if slot_minutes < start_minutes or slot_minutes > end_minutes:
        return None

    return time(hour=slot_minutes // 60, minute=slot_minutes % 60)


def _build_daily_summary(config, run_date):
    """Generate list of scheduled alert timestamps for the day."""
    alert_start_minutes = _minutes_since_midnight(config['alert_start'])  # Start offset.
    alert_end_minutes = _minutes_since_midnight(config['alert_end'])  # End offset.
    interval = config['interval_minutes']  # Slot spacing.

    summary_slots = []  # Will collect all slot labels.
    current = alert_start_minutes  # Loop pointer starts at alert window start.
    while current <= alert_end_minutes:
        hour = current // 60  # Convert minutes -> hour part.
        minute = current % 60  # Convert minutes -> minute part.
        summary_slots.append(f'{run_date.isoformat()} {hour:02d}:{minute:02d}')  # Add formatted slot.
        current += interval  # Advance to next slot.

    return summary_slots


def _display_datetime(now_utc, config):
    """Convert UTC datetime into configured display timezone."""
    return now_utc.astimezone(ZoneInfo(config['display_timezone']))


def _display_timestamp(now_utc, config):
    """Convert UTC datetime to display timezone and return formatted string."""
    return _display_datetime(now_utc, config).strftime(TIMESTAMP_FORMAT)


def _build_message_context(config, now_utc, scheduled_time=None):
    """Build common template fields for Telegram messages."""
    timezone_name = config['display_timezone']
    now_local = _display_datetime(now_utc, config)
    scheduled_dt = None
    if scheduled_time is not None:
        scheduled_dt = datetime.combine(now_local.date(), scheduled_time, tzinfo=ZoneInfo(timezone_name))

    return {
        'timestamp': now_local.strftime(TIMESTAMP_FORMAT),  # Backward-compatible field.
        'actual_run_time': now_local.strftime(TIMESTAMP_FORMAT),
        'scheduled_slot_time': scheduled_time.strftime(TIME_FORMAT) if scheduled_time else '',
        'scheduled_slot_timestamp': scheduled_dt.strftime(TIMESTAMP_FORMAT) if scheduled_dt else '',
        'display_timezone': timezone_name,
    }


def _process_scheduled_logic(config, now):
    """Process one scheduled run for market-hour alerts only.

    Scheduled mode intentionally sends only interval alerts inside market hours.
    Startup/run-start/summary signals are not emitted to avoid noisy Telegram logs.
    """
    # Compare in display timezone – configured times (08:00, 09:30 …) are local IST, not UTC.
    now_local = _display_datetime(now, config)
    now_time = now_local.time().replace(second=0, microsecond=0)

    # Read schedule values from config dict.
    execution_start = config['execution_start']
    execution_stop = config['execution_stop']
    alert_start = config['alert_start']
    alert_end = config['alert_end']
    tolerance_minutes = config['slot_tolerance_minutes']
    max_catchup_minutes = config['max_catchup_minutes']
    effective_slot_delay_limit = min(tolerance_minutes, max_catchup_minutes)
    now_minutes = _minutes_since_midnight(now_time)

    # If current time is outside execution window, do nothing.
    if not _is_inclusive_window(now_time, execution_start, execution_stop):
        logging.info(
            'Outside execution window; no action taken. now_local=%s execution=%s-%s (%s)',
            now_time.strftime(TIME_FORMAT),
            execution_start.strftime(TIME_FORMAT),
            execution_stop.strftime(TIME_FORMAT),
            config['display_timezone'],
        )
        return

    # Alert branch: process latest alert slot at/before run time inside market hours.
    latest_slot = _find_latest_slot_at_or_before(
        now_time,
        alert_start,
        alert_end,
        config['interval_minutes'],
    )
    if latest_slot is not None:
        latest_slot_minutes = _minutes_since_midnight(latest_slot)
        alert_delay = now_minutes - latest_slot_minutes
    else:
        alert_delay = None

    if latest_slot is not None and alert_delay is not None and 0 <= alert_delay <= effective_slot_delay_limit:
        alert_context = _build_message_context(config, now, latest_slot)
        alert_message = config['alert_template'].format(**alert_context)
        send_telegram_alert(config, alert_message)
        logging.info(
            'Alert slot processed. now_local=%s slot=%s delay=%s min alert_window=%s-%s interval=%s min delay_limit=%s min (%s)',
            now_time.strftime(TIME_FORMAT),
            latest_slot.strftime(TIME_FORMAT),
            alert_delay,
            alert_start.strftime(TIME_FORMAT),
            alert_end.strftime(TIME_FORMAT),
            config['interval_minutes'],
            effective_slot_delay_limit,
            config['display_timezone'],
        )
        return

    # If none of the above branches matched, this run is a no-op.
    logging.info(
        'Inside execution window, but no due alert slot. now_local=%s delay_limit=%s min (%s)',
        now_time.strftime(TIME_FORMAT),
        effective_slot_delay_limit,
        config['display_timezone'],
    )


def _run_local_continuous_mode(config):
    """Local runner: evaluates schedule continuously without changing GitHub behavior."""
    logging.info(
        'Local continuous mode enabled. Watching schedule in %s every %s second(s).',
        config['display_timezone'],
        config['local_loop_sleep_seconds'],
    )
    last_processed_minute = None  # Tracks last handled minute to avoid duplicate processing.

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)  # Current UTC minute tick.
        if now != last_processed_minute:
            _process_scheduled_logic(config, now)  # Process once per minute boundary.
            last_processed_minute = now  # Save current minute as processed.

        time_module.sleep(config['local_loop_sleep_seconds'])  # Poll delay.


def main():
    """One-shot run for scheduled CI execution.

    The job is expected to run on the configured cron schedule. Based on current UTC time,
    this function decides whether to send a market-hour alert slot or no-op.
    """
    config = _load_config()  # Load and normalize all env values.
    _validate_config(config)  # Fail fast if config has missing/invalid values.

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)  # Current UTC minute.
    logging.info(
        'Run context: utc_now=%s display_now=%s execution=%s-%s alert=%s-%s interval=%s min tolerance=%s min catchup=%s min',
        now.strftime(TIMESTAMP_FORMAT),
        _display_timestamp(now, config),
        config['execution_start'].strftime(TIME_FORMAT),
        config['execution_stop'].strftime(TIME_FORMAT),
        config['alert_start'].strftime(TIME_FORMAT),
        config['alert_end'].strftime(TIME_FORMAT),
        config['interval_minutes'],
        config['slot_tolerance_minutes'],
        config['max_catchup_minutes'],
    )

    # Manual-test mode: bypass schedule and send a test message immediately.
    if config['manual_test_mode']:
        manual_context = _build_message_context(config, now)
        manual_test_message = config['manual_test_template'].format(
            **manual_context,
        )
        sent = send_telegram_alert(config, manual_test_message)
        if not sent:
            raise RuntimeError('Manual test mode failed: Telegram message was not delivered. Check logs for API error details.')
        logging.info('Manual test mode processed.')
        return

    # Local continuous mode: run as loop for local machine testing/debug.
    if config['local_continuous_mode']:
        _run_local_continuous_mode(config)
        return

    # Normal GitHub Actions behavior: evaluate one scheduled run and exit.
    _process_scheduled_logic(config, now)


# Standard Python entrypoint guard.
if __name__ == '__main__':
    main()  # Start app when file is executed directly.

