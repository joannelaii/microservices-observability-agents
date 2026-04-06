import datetime

from .backend import llm_and_embeddings
llm = llm_and_embeddings()["llm"]

# Incident dictionary
INCIDENT_TYPE_KEYWORDS = {
    "crash_loop": ["crashloopbackoff", "crash loop", "oomkilled", "pod restart"],
    "latency": ["p95", "p99", "latency", "timeout", "slow", "response time"],
    "error_rate": ["error rate", "5xx", "http error", "failed request", "http_errors"],
    "memory": ["memory", "oom", "heap", "rss", "resident_memory"],
    "cpu": ["cpu", "throttl", "cpu_seconds", "cpu usage"],
    "database": ["database", "db", "postgres", "mysql", "query time", "connection pool"],
    "network": ["network", "dns", "connection refused", "unreachable", "packet loss"],
}

# Rule-based severity mapping
SEVERITY_KEYWORDS = {
    "p1": [
        "critical", "down", "unavailable", "outage", "crash", "oomkilled",
        "crashloopbackoff", "5xx error rate", "service down", "total failure",
    ],
    "p2": [
        "latency", "slow", "timeout", "error rate", "high cpu", "high memory",
        "degraded", "performance", "connection pool", "queue", "warning",
    ],
    "p3": [
        "minor", "informational", "debug",
    ],
}

def classify_alert_payload(payload: dict | None) -> dict[str, str]:
    """Classify incident_type/severity and compute query_window from payload."""
    if not payload:
        return {
            "incident_type": "unknown",
            "severity": "p3",
            "query_window": "unknown",
        }

    incident_type = "unknown"
    payload_text = alert_payload_to_text(payload).lower()
    severity = severity_from_text(payload_text)

    # Check alert labels first (more reliable than free text).
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {}) or {}
        alert_class = str(labels.get("class") or "").strip().lower()
        if alert_class in INCIDENT_TYPE_KEYWORDS:
            incident_type = alert_class

    # Fallback to keyword scanning if class labels are missing.
    if incident_type == "unknown":
        for itype, keywords in INCIDENT_TYPE_KEYWORDS.items():
            if any(kw in payload_text for kw in keywords):
                incident_type = itype
                break

    return {
        "incident_type": incident_type,
        "severity": severity,
        "query_window": query_window_from_payload(payload),
    }

def alert_payload_to_text(payload: dict) -> str:
    """Flatten alert payload into searchable text for LLM formatting and triage."""
    if not payload:
        return ""

    parts = [
        f"incident_key={payload.get('incident_key')}",
        f"scope={payload.get('scope')}",
        f"severity={payload.get('severity')}",
        f"start_time={payload.get('start_time')}",
        f"end_time={payload.get('end_time')}",
        f"alert_names={','.join(payload.get('alert_names', []))}",
    ]

    for alert in payload.get("alerts", [])[:5]:
        labels = alert.get("labels", {}) or {}
        annotations = alert.get("annotations", {}) or {}
        parts.append(
            " | ".join(
                [
                    f"alertname={alert.get('alertname')}",
                    f"class={labels.get('class')}",
                    f"label_severity={labels.get('severity')}",
                    f"summary={annotations.get('summary')}",
                    f"description={annotations.get('description')}",
                    f"value={alert.get('value')}",
                    f"state={alert.get('state')}",
                ]
            )
        )

    return "\n".join(parts)

def query_window_from_payload(payload: dict | None) -> str:
    """Compute query window from payload start/end times."""
    if not payload:
        return "unknown"

    start_time = str(payload.get("start_time") or "").strip()
    end_time = str(payload.get("end_time") or "").strip()
    if not start_time or not end_time:
        return "unknown"

    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        duration_seconds = int((end_dt - start_dt).total_seconds())
        if duration_seconds <= 0:
            return "unknown"
        return format_duration_seconds(duration_seconds)
    except Exception:
        return "unknown"

def severity_from_text(text: str) -> str:
    """Determine severity using a single keyword map."""
    lowered = (text or "").lower()
    for sev_level in ["p1", "p2", "p3"]:
        if any(keyword in lowered for keyword in SEVERITY_KEYWORDS[sev_level]):
            return sev_level
    return "p3"

def format_duration_seconds(total_seconds: int) -> str:
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    return f"{total_seconds // 3600}h"

