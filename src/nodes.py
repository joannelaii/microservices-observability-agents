from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.backend import llm_and_embeddings
from .prompts import (
    CODING_AGENT_SYSTEM_PROMPT,
    MAIN_AGENT_SYSTEM_PROMPT,
    REASONING_AGENT_SYSTEM_PROMPT,
    SUMMARISER_SYSTEM_PROMPT,
)
from .state import DiagnosticState
from dotenv import load_dotenv
from datetime import datetime
import uuid

load_dotenv()

llm = llm_and_embeddings()["llm"]

# Rule-based severity mapping
_SEVERITY_KEYWORDS = {
    "p1": [
        "critical",
        "down",
        "unavailable",
        "outage",
        "crash",
        "oomkilled",
        "crashloopbackoff",
        "5xx error rate",
        "service down",
        "total failure",
    ],
    "p2": [
        "latency",
        "slow",
        "timeout",
        "error rate",
        "high cpu",
        "high memory",
        "degraded",
        "performance",
        "connection pool",
        "queue",
        "warning",
    ],
    "p3": [
        "minor",
        "informational",
        "debug",
    ],
}

# Incident type keywords
_INCIDENT_TYPE_KEYWORDS = {
    "crash_loop": ["crashloopbackoff", "crash loop", "oomkilled", "pod restart"],
    "latency": ["p95", "p99", "latency", "timeout", "slow", "response time"],
    "error_rate": ["error rate", "5xx", "http error", "failed request", "http_errors"],
    "memory": ["memory", "oom", "heap", "rss", "resident_memory"],
    "cpu": ["cpu", "throttl", "cpu_seconds", "cpu usage"],
    "database": [
        "database",
        "db",
        "postgres",
        "mysql",
        "query time",
        "connection pool",
    ],
    "network": ["network", "dns", "connection refused", "unreachable", "packet loss"],
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


def _severity_from_text(text: str) -> str:
    """Determine severity using a single keyword map."""
    lowered = (text or "").lower()
    for sev_level in ["p1", "p2", "p3"]:
        if any(keyword in lowered for keyword in _SEVERITY_KEYWORDS[sev_level]):
            return sev_level
    return "p3"


def _format_duration_seconds(total_seconds: int) -> str:
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    return f"{total_seconds // 3600}h"


def _query_window_from_payload(payload: dict | None) -> str:
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
        return _format_duration_seconds(duration_seconds)
    except Exception:
        return "unknown"


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
    severity = _severity_from_text(payload_text)

    # Check alert labels first (more reliable than free text).
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {}) or {}
        alert_class = str(labels.get("class") or "").strip().lower()
        if alert_class in _INCIDENT_TYPE_KEYWORDS:
            incident_type = alert_class

    # Fallback to keyword scanning if class labels are missing.
    if incident_type == "unknown":
        for itype, keywords in _INCIDENT_TYPE_KEYWORDS.items():
            if any(kw in payload_text for kw in keywords):
                incident_type = itype
                break

    return {
        "incident_type": incident_type,
        "severity": severity,
        "query_window": _query_window_from_payload(payload),
    }


def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    """
    LLM-based input formatter.
    1. Trace flow: Format investigation request from trace_id + time_window.
    2. Alert flow: Format investigation request from alert payload.

    Returns state with diagnostic_plan.
    """
    import sys

    print("=== MAIN AGENT NODE ===", file=sys.stderr)

    if state.get("trace_id"):
        trace_id = state["trace_id"]
        time_window = state.get("time_window", "5m")
        query = f"Investigate trace ID: {trace_id} over {time_window}"
        print(f"[MAIN AGENT] Trace investigation: {query}", file=sys.stderr)
        return {**state, "diagnostic_plan": query}

    alert_payload = state.get("alert_payload")
    alert_context = alert_payload_to_text(alert_payload) if alert_payload else ""
    if alert_context:
        try:
            messages = [
                SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
                HumanMessage(content=f"Alert to investigate:\n{alert_context}"),
            ]
            response = llm.invoke(messages)
            query = response.content if hasattr(response, "content") else str(response)
            print(f"[MAIN AGENT] Alert investigation: {query}...", file=sys.stderr)
            return {**state, "diagnostic_plan": query}
        except Exception as e:
            print(f"[MAIN AGENT] Error processing alert: {e}", file=sys.stderr)
            return {**state, "diagnostic_plan": alert_context, "error": str(e)}

    return {**state, "diagnostic_plan": "No trace ID or alert payload provided"}


def triage_node(state: DiagnosticState) -> DiagnosticState:
    """
    Rule-based severity classifier. Determines:
    - incident_type
    - severity
    - query
    """
    import sys

    if state.get("trace_id"):
        triage_metadata = {
            "incident_type": "trace_investigation",
            "severity": "p2",
            "query_window": state.get("time_window", "1h"),
            "query": (
                f"Diagnose request failure using trace_id={state['trace_id']}. "
                "Investigate error spans, downstream service failures, and latency spikes."
            ),
        }
    else:
        payload_cls = classify_alert_payload(state.get("alert_payload"))
        incident_type = payload_cls["incident_type"]
        severity = payload_cls["severity"]
        query_window = payload_cls["query_window"]
        query = f"Investigate {incident_type} issue from alert payload"

        triage_metadata = {
            "incident_type": incident_type,
            "severity": severity,
            "query_window": query_window,
            "query": query,
        }

    query = triage_metadata.get("query", "")
    tool_call = {
        "id": str(uuid.uuid4()),
        "name": "retrieve_sop",
        "args": {"query": query},
    }

    print(
        f"==========Triage: {triage_metadata['incident_type'].upper()} [{triage_metadata['severity'].upper()}]===========",
        file=sys.stderr,
    )
    print(f"Triage Query: {triage_metadata}", file=sys.stderr)

    return {
        **state,
        "messages": (state.get("messages") or [])
        + [AIMessage(content="", tool_calls=[tool_call])],
        "triage_metadata": triage_metadata,
    }


# Code Expert Node
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    coding_task = (
        state.get("coding_task")
        or "Analyse the available telemetry and write a focused diagnostic script."
    )

    messages = [
        SystemMessage(content=CODING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident Context
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## SOP Guidance
            {state.get("sop_guidance") or "None"}

            ## Task from Reasoning Agent
            {coding_task}

            Write the Python code (e.g. function/script) required to accomplish this task.
            """
        ),
    ]
    response = llm.invoke(messages)
    print("==========Code Expert==========")
    print(f"\nCode Expert response:\n{response.content}")
    return {**state, "code_analysis": response.content}


# Reasoning Node
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
            ## Incident
            Service: {state["service_name"]}
            Alert / Telemetry: {state["telemetry"]}

            ## Evidence Gathered
            SOP Guidance:
            {state.get("sop_guidance") or "Not yet gathered"}

            Code Analysis:
            {state.get("code_analysis") or "Not yet gathered"}

            Decide the next step to be carried out based on the information gathered so far.
            """
        ),
    ]
    response = llm.invoke(messages)
    content = response.content.strip()

    next_action = content.split("\n")[0].strip()

    # extract coding task to pass to the coding agent for execution
    coding_task = None
    if "CODING TASK:" in content:
        coding_task = content.split("CODING TASK:", 1)[1].strip()

    print("==========Reasoning Agent==========")
    print(f"\nReasoning Agent response:\n{content}")

    return {
        **state,
        "reasoning_output": content,
        "next_action": next_action,
        "coding_task": coding_task,
    }


# Summariser Node
def run_summariser_node(state: DiagnosticState) -> DiagnosticState:
    messages = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Telemetry: {state["telemetry"]}\n
        Service: {state["service_name"]}\n

        SOP Agent:\n
        {state.get("sop_guidance", "N/A")}\n

        Code Expert:\n
        {state.get("code_analysis", "N/A")}\n

        Reasoning Agent:\n
        {state.get("reasoning_output", "N/A")}\n
            """
        ),
    ]
    response = llm.invoke(messages)
    print("==========Summariser Agent==========")
    # print(f"\nSummariser Agent returned:\n {response.content}")
    return {**state, "summary": response.content}


# TODO: implement this function
def run_best_effort_node(state: DiagnosticState) -> DiagnosticState:
    return {**state, "best_effort": "STUB: best_effort_node not yet implemented"}
