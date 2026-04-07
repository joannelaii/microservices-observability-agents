import json
import subprocess
import heapq
import time
from datetime import datetime, timezone
from itertools import count
import os
import sys

import requests
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from src.bot import build_diagnosis_message, send_diagnosis, start_bot_thread
else:
    from .bot import build_diagnosis_message, send_diagnosis, start_bot_thread

from graphs.root_graph import build_graph
from common.util import classify_alert_payload


PROM_ALERTS_URL = "http://localhost:9090/api/v1/alerts"
POLL_INTERVAL = 10
TRIGGER_COOLDOWN = 300
TIMEOUT = 5
TELEGRAM_TIMEOUT = 10

SEVERITY_TO_PRIORITY = {
    "p1": 0,
    "p2": 1,
    "p3": 2,
}

ALERT_GROUP_MAP = {
    "FrontendCheckoutErrorRateHigh": "frontend:symptom",
    "FrontendCheckoutFailuresPresent": "frontend:symptom",
    "FrontendOverallErrorRateHigh": "frontend:symptom",
    "CheckoutTrafficDrop": "frontend:symptom",
    "FrontendTrafficDrop": "frontend:symptom",
    "FrontendLatencyHigh": "frontend:symptom",
    "ServiceRestartDetected": "infrastructure:restart",
}


def incident_key(alert: dict) -> str:
    alertname = alert.get("labels", {}).get("alertname", "unknown")
    return ALERT_GROUP_MAP.get(alertname, f"ungrouped:{alertname}")


def parse_active_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def build_incident_payload(key: str, group_alerts: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    start_dt = datetime.fromtimestamp(now.timestamp() - 600, tz=timezone.utc)

    alerts_payload = []
    alert_names = []

    for alert in group_alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alertname = labels.get("alertname")

        if alertname:
            alert_names.append(alertname)

        alerts_payload.append(
            {
                "alertname": alertname,
                "labels": labels,
                "annotations": annotations,
                "state": alert.get("state"),
                "active_at": parse_active_time(alert.get("activeAt")),
                "value": alert.get("value"),
            }
        )

    first_labels = group_alerts[0].get("labels", {}) if group_alerts else {}

    return {
        "incident_key": key,
        "service_name": first_labels.get("service_name"),
        "scope": first_labels.get("scope"),
        "severity": first_labels.get("severity"),
        "start_time": start_dt.isoformat(),
        "end_time": now.isoformat(),
        "alert_names": sorted(set(alert_names)),
        "alerts": alerts_payload,
    }


def diagnose(payload: dict) -> None:
    print(f"[TRIGGER] {json.dumps(payload, ensure_ascii=False)}")

    graph = _get_graph()
    alert_context = _payload_to_alert_context(payload)
    service_name = payload.get("service_name") or "opentelemetry-collector"

    started = time.perf_counter()
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=alert_context)],
            "telemetry": "",
            "service_name": service_name,
            "start_time": payload.get("start_time"),
            "end_time": payload.get("end_time"),
            "trace_id": None,
            "time_window": None,
            "alert_payload": payload,
            "triage_metadata": None,
            "diagnostic_plan": None,
            "sop_guidance": None,
            "code_analysis": None,
            "reasoning_output": None,
            "next_action": "",
            "summary": None,
            "error": None,
            "meta_input_tokens": 0,
            "meta_output_tokens": 0,
            "meta_total_tokens": 0,
            "meta_duration_s": None,
        }
    )
    result["meta_duration_s"] = time.perf_counter() - started

    triage_metadata = result.get("triage_metadata") or {}
    summary = result.get("summary")
    if summary is None:
        raise ValueError("Summariser did not return a Diagnosis object.")

    message = build_diagnosis_message(payload, triage_metadata, summary, result)
    send_diagnosis(message)


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _payload_to_alert_context(payload: dict) -> str:
    alert_names = ", ".join(payload.get("alert_names", [])) or "unknown"
    incident_key_value = payload.get("incident_key") or "unknown"
    scope = payload.get("scope") or "unknown"
    severity = payload.get("severity") or "unknown"

    details: list[str] = []
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {}) or {}
        annotations = alert.get("annotations", {}) or {}
        details.append(
            " | ".join(
                [
                    f"alertname={alert.get('alertname')}",
                    f"class={labels.get('class')}",
                    f"label_severity={labels.get('severity')}",
                    f"summary={annotations.get('summary')}",
                    f"description={annotations.get('description')}",
                    f"value={alert.get('value')}",
                ]
            )
        )

    details_text = "\n".join(details) if details else "details=none"
    return (
        f"incident_key={incident_key_value}\n"
        f"scope={scope}\n"
        f"severity={severity}\n"
        f"alert_names={alert_names}\n"
        f"start_time={payload.get('start_time')}\n"
        f"end_time={payload.get('end_time')}\n"
        f"{details_text}"
    )


def _queue_priority_from_payload(payload: dict) -> int:
    cls = classify_alert_payload(payload)
    return SEVERITY_TO_PRIORITY.get(cls.get("severity", "p3"), SEVERITY_TO_PRIORITY["p3"])



def fetch_alerts() -> list[dict]:
    r = requests.get(PROM_ALERTS_URL, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("alerts", [])


def main() -> None:
    triggered_timestamp: dict[str, float] = {}
    firing: set[str] = set()
    alert_queue: list[tuple[int, float, int, str, dict]] = []
    queue_counter = count()
    start_bot_thread()

    try:
        while True:
            now = time.time()

            try:
                alerts = fetch_alerts()
            except Exception as e:
                print(f"[ERROR] failed to fetch alerts: {e}")
                time.sleep(POLL_INTERVAL)
                continue

            alerts_fired = [a for a in alerts if a.get("state") == "firing"]

            groups: dict[str, list[dict]] = {}
            for alert in alerts_fired:
                key = incident_key(alert)
                groups.setdefault(key, []).append(alert)

            is_fired: set[str] = set(groups.keys())

            for key, group_alerts in groups.items():
                cooldown_expired = now - triggered_timestamp.get(key, 0) >= TRIGGER_COOLDOWN

                if key not in firing or cooldown_expired:
                    payload = build_incident_payload(key, group_alerts)
                    priority = _queue_priority_from_payload(payload)
                    heapq.heappush(
                        alert_queue,
                        (priority, now, next(queue_counter), key, payload),
                    )
                    triggered_timestamp[key] = now

                    # TODO: for test purposes, breaks after the first alert group is queued.
                    break

            while alert_queue:
                _, _, _, queue_key, queue_payload = heapq.heappop(alert_queue)
                print(f"[QUEUE] Processing {queue_key}")
                try:
                    diagnose(queue_payload)
                except Exception as exc:
                    print(f"[ERROR] diagnosis failed for {queue_key}: {exc}")

            resolved_keys = firing - is_fired
            for key in resolved_keys:
                firing.remove(key)

            firing |= is_fired

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Closed by user.")


if __name__ == "__main__":
    main()
