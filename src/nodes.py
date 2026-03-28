from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.backend import llm_and_embeddings
from .prompts import MAIN_AGENT_SYSTEM_PROMPT, SUMMARISER_SYSTEM_PROMPT
from .state import DiagnosticState
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

llm = llm_and_embeddings()["llm"]

# Rule-based severity mapping
_SEVERITY_KEYWORDS = {
    "p1": [
        "critical", "down", "unavailable", "outage", "crash", "oomkilled",
        "crashloopbackoff", "5xx error rate", "service down", "total failure",
    ],
    "p2": [
        "latency", "slow", "timeout", "error rate", "high cpu", "high memory",
        "degraded", "performance", "connection pool", "queue",
    ],
    "p3": [
        "warning", "minor", "informational", "debug",
    ],
}

# Incident type keywords
_INCIDENT_TYPE_KEYWORDS = {
    "crash_loop": ["crashloopbackoff", "crash loop", "oomkilled", "pod restart"],
    "latency": ["p95", "p99", "latency", "timeout", "slow", "response time"],
    "error_rate": ["error rate", "5xx", "http error", "failed request", "http_errors"],
    "memory": ["memory", "oom", "heap", "rss", "resident_memory"],
    "cpu": ["cpu", "throttl", "cpu_seconds", "cpu usage"],
    "database": ["database", "db", "postgres", "mysql", "query time", "connection pool"],
    "network": ["network", "dns", "connection refused", "unreachable", "packet loss"],
}


def run_main_agent_node(state: DiagnosticState) -> DiagnosticState:
    """
    LLM-based input formatter. Processes either:
    1. Trace ID investigations: Format as "Investigate trace ID: {trace_id} over {time_window}"
    2. Alert processing: Process alert text into investigation query
    
    Returns state with diagnostic_plan (formatted investigation query).
    """
    import sys
    print("=== MAIN AGENT NODE ===", file=sys.stderr)
    
    # Check if this is a trace ID investigation
    if state.get("trace_id"):
        trace_id = state["trace_id"]
        time_window = state.get("time_window", "5m")
        
        # Format investigation query for trace
        query = f"Investigate trace ID: {trace_id} over {time_window}"
        
        print(f"[MAIN AGENT] Trace investigation: {query}", file=sys.stderr)
        return {**state, "diagnostic_plan": query}
    
    # Otherwise, process alert input (from telemetry)
    telemetry = state.get("telemetry", "")
    if telemetry:
        # Use LLM to format alert into investigation query
        try:
            messages = [
                SystemMessage(content=MAIN_AGENT_SYSTEM_PROMPT),
                HumanMessage(content=f"Alert to investigate:\n{telemetry}"),
            ]
            
            response = llm.invoke(messages)
            query = response.content if hasattr(response, 'content') else str(response)
            
            print(f"[MAIN AGENT] Alert investigation: {query}...", file=sys.stderr)
            return {**state, "diagnostic_plan": query}
        except Exception as e:
            print(f"[MAIN AGENT] Error processing alert: {e}", file=sys.stderr)
            # Fallback: use telemetry as-is
            return {**state, "diagnostic_plan": telemetry, "error": str(e)}
    
    # Fallback: no trace ID or telemetry provided
    return {**state, "diagnostic_plan": "No trace ID or alert telemetry provided"}


def triage_node(state: DiagnosticState) -> DiagnosticState:
    """
    Rule-based severity classifier. Uses keyword matching to determine:
    - incident_type (latency, error_rate, memory, cpu, crash_loop, database, network, trace_investigation)
    - severity (p1, p2, p3)
    - query_window (derived from incident type)
    - query (formatted investigation query)
    """
    import sys
    
    # For trace investigations, use fixed metadata
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
        # For alarms, classify by keyword matching
        alarm_text = (state.get("telemetry") or "").lower()
        
        # Determine incident type by keyword matching
        incident_type = "unknown"
        for itype, keywords in _INCIDENT_TYPE_KEYWORDS.items():
            if any(kw in alarm_text for kw in keywords):
                incident_type = itype
                break
        
        # Determine severity by keyword matching
        severity = "p3"
        for sev_level in ["p1", "p2"]:
            if any(kw in alarm_text for kw in _SEVERITY_KEYWORDS[sev_level]):
                severity = sev_level
                break
        
        # Set query window based on incident type
        query_window_map = {
            "crash_loop": "10m",
            "latency": "30m",
            "error_rate": "15m",
            "memory": "20m",
            "cpu": "20m",
            "database": "30m",
            "network": "15m",
        }
        query_window = query_window_map.get(incident_type, "30m")
        
        # Build formatted query
        query = f"Investigate {incident_type} issue from alert: {state.get('telemetry', '')[:200]}"
        
        triage_metadata = {
            "incident_type": incident_type,
            "severity": severity,
            "query_window": query_window,
            "query": query,
        }
    
    # Create tool call for SOP retrieval
    query = triage_metadata["query"]
    tool_call = {
        "id": str(uuid.uuid4()),
        "name": "retrieve_sop",
        "args": {"query": query},
    }

    print(f"==========Triage: {triage_metadata['incident_type'].upper()} [{triage_metadata['severity'].upper()}]===========", file=sys.stderr)
    print(f"Triage Query: {triage_metadata}", file=sys.stderr)
    

    return {
        **state,
        "messages": (state.get("messages") or []) + [AIMessage(content="", tool_calls=[tool_call])],
        "triage": "sop_tool",
        "triage_metadata": triage_metadata,
    }


# SOP Node
# def run_sop_node(state: DiagnosticState) -> DiagnosticState:
#     # Call SOP agent via shared helper
#     sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "sop-agent", "sops")
#     sop_dir = os.path.abspath(sop_dir)
#
#     result = run_sop_agent(telemetry=state["telemetry"], sop_dir=sop_dir)
#     print("==========SOP Agent==========")
#     print(f"\nSOP Agent returned:\n {result.get('answer', '')}")
#     return {**state, "sop_guidance": result.get("answer", "")}


# Code Expert Node, change to use code expert agent when implemented
def run_code_expert_node(state: DiagnosticState) -> DiagnosticState:
    # messages = []
    # response = llm.invoke(messages)
    # return {**state, "code_analysis": response.content}
    print("==========Code Expert==========")
    # print(f"Code Generated:\n {response.content}")
    return {**state, "code_analysis": "STUB: Code expert not yet implemented"}


# Reasoning Node, change to use reasoning agent when implemented
def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    # messages = []
    # response = llm.invoke(messages)
    # return {**state, "reasoning_output": response.content}
    print("==========Reasoning Agent==========")
    # print(f"Reasoning Agent returned:\n {response.content}")
    # TODO: Bind tool call to llm invoke
    return {
        **state,
        "reasoning_output": "STUB: Reasoning agent not yet implemented",
        "root_cause_found": True,
        # Hard coded next action for testing but I think there needs to be some logic here to decide what the next action is since the graph uses a route_next function to determine the next node
        "next_action": "synthesize_diagnosis",
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

