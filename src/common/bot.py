import os
import html
import requests
from datetime import datetime, timezone, timedelta

from .state import Diagnosis

TELEGRAM_TIMEOUT = 10

def build_diagnosis_message(payload: dict, triage_metadata: dict, summary: Diagnosis) -> str:
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
        f"<b>Alert Window:</b> {format_time_range(payload.get("start_time"), payload.get("end_time"))}",
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
        parts.extend(f"• {html.escape(x)}" for x in summary.evidence)
    else:
        parts.append("• None")

    if summary.recommended_actions:
        parts.extend([
            "",
            "<b>RECOMMENDED ACTIONS:</b>",
        ])
        parts.extend(f"• {html.escape(x)}" for x in summary.recommended_actions)

    if summary.next_investigation_steps:
        parts.extend([
            "",
            "<b>NEXT INVESTIGATION STEPS:</b>",
        ])
        parts.extend(f"• {html.escape(x)}" for x in summary.next_investigation_steps)

    return "\n".join(parts)

def send_diagnosis(text: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")

    missing = []
    if not token:
        missing.append("TELEGRAM_TOKEN")
    if not chat_ids:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        print(f"[WARN] Missing {', '.join(missing)}; skipping telegram send.")
        return

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in [cid.strip() for cid in chat_ids.split(",") if cid.strip()]:
        try:
            requests.post(
                endpoint,
                json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML"},
                timeout=TELEGRAM_TIMEOUT,
            ).raise_for_status()
        except Exception as exc:
            print(f"[ERROR] Failed to send diagnosis to chat_id={chat_id}: {exc}")

SGT = timezone(timedelta(hours=8))

def format_time_range(start_iso, end_iso) -> str:
    if not start_iso or not end_iso:
        return "Time window unavailable"

    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(SGT)
    end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(SGT)

    start_str = f"{start_dt.day} {start_dt.strftime('%b %y %I:%M%p')}"
    end_str = f"{end_dt.day} {end_dt.strftime('%b %y %I:%M%p')}"
    return f"{start_str} - {end_str}"