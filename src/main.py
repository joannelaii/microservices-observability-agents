import json
import subprocess
import time
from datetime import datetime, timezone

import requests


PROM_ALERTS_URL = "http://localhost:9090/api/v1/alerts"
POLL_INTERVAL = 10
TRIGGER_COOLDOWN = 300
TIMEOUT = 5

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
        "scope": first_labels.get("scope"),
        "severity": first_labels.get("severity"),
        "start_time": start_dt.isoformat(),
        "end_time": now.isoformat(),
        "alert_names": sorted(set(alert_names)),
        "alerts": alerts_payload,
    }


def diagnose(payload: dict) -> None:
    print(f"[TRIGGER] {json.dumps(payload, ensure_ascii=False)}")
    # TODO add entrypoint for invoking graph



def fetch_alerts() -> list[dict]:
    r = requests.get(PROM_ALERTS_URL, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("data", {}).get("alerts", [])


def main() -> None:
    triggered_timestamp: dict[str, float] = {}
    firing: set[str] = set()

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
                    diagnose(payload)
                    triggered_timestamp[key] = now

            resolved_keys = firing - is_fired
            for key in resolved_keys:
                firing.remove(key)

            firing |= is_fired

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Closed by user.")


if __name__ == "__main__":
    main()