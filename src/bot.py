import asyncio
import html
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from itertools import count
from queue import PriorityQueue
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .common.state import Diagnosis
TELEGRAM_TIMEOUT = 10
SGT = timezone(timedelta(hours=8))
TELEGRAM_REQUEST_PRIORITY = 100
_BOT_THREAD: Optional[threading.Thread] = None
_BOT_LOOP: Optional[asyncio.AbstractEventLoop] = None
_BOT_APP: Optional[Application] = None
_BOT_READY = threading.Event()
WORK_QUEUE: PriorityQueue = PriorityQueue()
_QUEUE_COUNTER = count()


def build_diagnosis_message(
    payload: dict,
    triage_metadata: dict,
    summary: Diagnosis,
    metadata: dict | None = None,
) -> str:
    incident_key_value = payload.get("alert_names") or ["unknown"]
    if isinstance(incident_key_value, list):
        incident_text = ", ".join(str(x) for x in incident_key_value)
    else:
        incident_text = str(incident_key_value)

    triage_severity = triage_metadata.get("severity", "unknown")
    incident_type = triage_metadata.get("incident_type", "unknown")

    parts = [
        f"<b>Incident:</b> {html.escape(incident_text)}",
        f"<b>Triage:</b> {html.escape(f'{incident_type} [{triage_severity}]')}",
        "",
        f"<b>Summary:</b> {html.escape(summary.incident.summary)}",
        f"<b>Service:</b> {html.escape(summary.incident.service)}",
        f"<b>Alert Window:</b> {format_time_range(payload.get('start_time'), payload.get('end_time'))}",
        "",
        f"<b>ROOT CAUSE STATUS:</b> {html.escape(summary.root_cause_status)}",
    ]

    if summary.root_cause_found and summary.root_cause:
        parts.extend([
            "",
            f"<b>ROOT CAUSE:</b> {html.escape(summary.root_cause)}",
        ])

    parts.extend([
        "",
        f"<b>REASON:</b> {html.escape(summary.reason)}",
        "",
        "<b>EVIDENCE:</b>",
    ])

    if summary.evidence:
        parts.extend(f"- {html.escape(x)}" for x in summary.evidence)
    else:
        parts.append("- None")

    if summary.recommended_actions:
        parts.extend([
            "",
            "<b>RECOMMENDED ACTIONS:</b>",
        ])
        parts.extend(f"- {html.escape(x)}" for x in summary.recommended_actions)

    if summary.next_investigation_steps:
        parts.extend([
            "",
            "<b>NEXT INVESTIGATION STEPS:</b>",
        ])
        parts.extend(f"- {html.escape(x)}" for x in summary.next_investigation_steps)

    if metadata:
        duration_s = metadata.get("meta_duration_s")
        input_tokens = int(metadata.get("meta_input_tokens", 0) or 0)
        output_tokens = int(metadata.get("meta_output_tokens", 0) or 0)
        total_tokens = int(metadata.get("meta_total_tokens", 0) or 0)
        duration_text = f"{duration_s:.2f}s" if isinstance(duration_s, (int, float)) else "N/A"
        parts.extend([
            "",
            "----------------------",
            "<b>METADATA</b>",
            f"Duration: {html.escape(duration_text)}",
            f"Tokens: {input_tokens} in / {output_tokens} out / {total_tokens} total",
        ])

    return "\n".join(parts)


def format_time_range(start_iso, end_iso) -> str:
    if not start_iso or not end_iso:
        return "Time window unavailable"

    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(SGT)
    end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(SGT)

    start_str = f"{start_dt.day} {start_dt.strftime('%b %y %I:%M%p')}"
    end_str = f"{end_dt.day} {end_dt.strftime('%b %y %I:%M%p')}"
    return f"{start_str} - {end_str}"


class ObservabilityBotManager:
    def __init__(self):
        pass

    @staticmethod
    def _detect_trace_id(text: str) -> str | None:
        text = text.strip().strip("'\"")
        if not text:
            return None

        if len(text) == 36 and text.count("-") == 4:
            try:
                int(text.replace("-", ""), 16)
                return text
            except ValueError:
                pass

        if re.fullmatch(r"[A-Fa-f0-9]{8,64}", text) and re.search(r"\d", text):
            return text

        if re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}", text) and re.search(r"\d", text):
            return text

        return None

    @classmethod
    def _extract_trace_and_window(cls, text: str) -> tuple[str | None, str | None]:
        raw = (text or "").strip()
        if not raw:
            return None, None

        prefixed = re.search(
            r"(?:trace[_\s-]?id)\s*[:=]?\s*(?P<trace>[A-Za-z0-9-]{8,})\s*(?:[,\s]\s*(?P<window>.*))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if prefixed:
            candidate = (prefixed.group("trace") or "").strip()
            trace_id = cls._detect_trace_id(candidate)
            if trace_id:
                return trace_id, cls._parse_time_window((prefixed.group("window") or "").strip())

        if "," in raw:
            first, rest = raw.split(",", 1)
            trace_id = cls._detect_trace_id(first.strip())
            if trace_id:
                return trace_id, cls._parse_time_window(rest.strip())

        whole = cls._detect_trace_id(raw)
        if whole:
            return whole, None

        first_token, sep, remainder = raw.partition(" ")
        token_trace = cls._detect_trace_id(first_token)
        if token_trace and sep:
            return token_trace, cls._parse_time_window(remainder.strip())

        return None, None

    @staticmethod
    def _parse_time_window(text: str) -> str | None:
        if not text:
            return None

        cleaned = text.strip().lower()
        match = re.fullmatch(
            r"(?P<value>\d+)\s*(?P<unit>m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)",
            cleaned,
        )
        if not match:
            return None

        value = match.group("value")
        unit = match.group("unit")
        if unit.startswith("m"):
            suffix = "m"
        elif unit.startswith("h"):
            suffix = "h"
        else:
            suffix = "d"
        return f"{value}{suffix}"


bot_manager = ObservabilityBotManager()


def enqueue_work(priority: int, item: dict) -> None:
    WORK_QUEUE.put(
        (
            priority,
            datetime.now(timezone.utc).timestamp(),
            next(_QUEUE_COUNTER),
            item,
        )
    )


def enqueue_trace_request(
    chat_id: int,
    text: str,
    service_name: str = "opentelemetry-collector",
) -> tuple[bool, str]:
    trace_id, _ = bot_manager._extract_trace_and_window(text)
    if not trace_id:
        return False, "Usage: send a trace ID or /diag <trace_id>"

    item = {
        "source": "telegram",
        "chat_id": chat_id,
        "trace_id": trace_id,
        "service_name": service_name,
    }
    enqueue_work(TELEGRAM_REQUEST_PRIORITY, item)
    return True, f"Queued trace investigation for {trace_id}"

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    ok, response = enqueue_trace_request(update.effective_chat.id, update.message.text)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)


async def on_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Usage: /diag <trace_id>\nExample: /diag abc123def456",
        )
        return

    ok, response = enqueue_trace_request(update.effective_chat.id, text)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "Welcome to Microservices Observability Bot!\n\n"
        "Send me:\n"
        "- A trace ID (e.g., 'abc123def456')\n"
        "- In groups: /diag <trace_id>\n\n"
        "I'll diagnose the issue and suggest fixes."
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome)


async def on_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    details = (
        f"chat_id={chat.id}\n"
        f"chat_type={chat.type}\n"
        f"chat_title={chat.title or 'N/A'}"
    )
    await context.bot.send_message(chat_id=chat.id, text=details)


def _build_app(token: str) -> Application:
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("chatid", on_chatid))
    app.add_handler(CommandHandler("diag", on_diag))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    return app


def _bot_thread_main(token: str) -> None:
    global _BOT_LOOP, _BOT_APP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _BOT_LOOP = loop
    _BOT_APP = _build_app(token)

    async def runner():
        await _BOT_APP.initialize()
        await _BOT_APP.start()
        await _BOT_APP.updater.start_polling()
        _BOT_READY.set()

    loop.run_until_complete(runner())
    print("Bot started (polling)")
    loop.run_forever()


def start_bot_thread() -> Optional[threading.Thread]:
    global _BOT_THREAD
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("[WARN] TELEGRAM_TOKEN not set; telegram bot not started.")
        return None

    if _BOT_THREAD and _BOT_THREAD.is_alive():
        return _BOT_THREAD

    _BOT_READY.clear()
    _BOT_THREAD = threading.Thread(
        target=_bot_thread_main,
        args=(token,),
        name="telegram-bot",
        daemon=True,
    )
    _BOT_THREAD.start()
    _BOT_READY.wait(timeout=10)
    return _BOT_THREAD


def send_diagnosis(text: str) -> None:
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_ids:
        print("[WARN] Missing TELEGRAM_CHAT_ID; skipping telegram send.")
        return
    if _BOT_LOOP is None or _BOT_APP is None:
        print("[WARN] Telegram bot runtime not started; skipping telegram send.")
        return

    async def sender() -> None:
        for chat_id in [cid.strip() for cid in chat_ids.split(",") if cid.strip()]:
            await _BOT_APP.bot.send_message(
                chat_id=chat_id,
                text=text[:4000],
                parse_mode="HTML",
            )

    try:
        future = asyncio.run_coroutine_threadsafe(sender(), _BOT_LOOP)
        future.result(timeout=TELEGRAM_TIMEOUT)
    except Exception as exc:
        print(f"[ERROR] Failed to send diagnosis via telegram bot runtime: {exc}")


def send_chat_message(chat_id: int, text: str, parse_mode: str | None = None) -> None:
    if _BOT_LOOP is None or _BOT_APP is None:
        print("[WARN] Telegram bot runtime not started; skipping chat send.")
        return

    async def sender() -> None:
        await _BOT_APP.bot.send_message(
            chat_id=chat_id,
            text=text[:4000],
            parse_mode=parse_mode,
        )

    try:
        future = asyncio.run_coroutine_threadsafe(sender(), _BOT_LOOP)
        future.result(timeout=TELEGRAM_TIMEOUT)
    except Exception as exc:
        print(f"[ERROR] Failed to send telegram chat message: {exc}")


def main():
    thread = start_bot_thread()
    if thread is None:
        return
    thread.join()


if __name__ == "__main__":
    main()
