from langchain_core.messages import HumanMessage, SystemMessage

from common.state import DiagnosticState
from common.util import alert_payload_to_text, classify_alert_payload, llm, usage_update
from .prompts import MAIN_AGENT_SYSTEM_PROMPT

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
            return {**state, "diagnostic_plan": query, **usage_update(state, response)}
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

    print(
        f"==========Triage: {triage_metadata['incident_type'].upper()} [{triage_metadata['severity'].upper()}]===========",
        file=sys.stderr,
    )
    print(f"Triage Query: {triage_metadata}", file=sys.stderr)

    return {
        **state,
        "triage_metadata": triage_metadata,
    }
