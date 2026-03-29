
"""
Test script to verify main-agent + triage flows work correctly.

Tests both alarm-based (SOP) and trace-id-based (telemetry) flows.
"""

import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Load env vars
load_dotenv()

# Ensure API key available (can use placeholder for testing)
if "OPENAI_API_KEY" not in os.environ:
    os.environ["OPENAI_API_KEY"] = "sk-placeholder-for-testing"

from src.graph import build_graph
from src.state import DiagnosticState


def test_alarm_flow():
    """Test Flow 1: Alarm triggered -> triage -> SOP_TOOL -> reasoning -> diagnosis"""
    print("\n" + "=" * 80)
    print("TEST 1: ALARM FLOW (telemetry -> SOP retrieval -> reasoning -> summary)")
    print("=" * 80 + "\n")

    graph = build_graph()

    alarm_telemetry = """
    source=prometheus
    timestamp_utc=2026-03-20T10:22:30Z
    
    k8s.namespace.name=observability
    k8s.pod.name=payment-service-6f9d7c7b9f-2k9lq
    
    metric.process_resident_memory_bytes=1900000000
    metric.container_cpu_seconds_total=4500.12
    k8s.container.memory_limit_bytes=2147483648
    
    metric.http_requests_total=45000
    metric.http_errors_total=1200
    """

    result = graph.invoke({
        "messages": [HumanMessage(content="High CPU usage detected in service")],
        "telemetry": alarm_telemetry,
        "service_name": "payment-service",
        "trace_id": None,  # No trace ID -> ALARM FLOW
        "diagnostic_plan": None,
        "sop_guidance": None,
        "code_analysis": None,
        "reasoning_output": None,
        "next_action": "",
        "summary": None,
        "error": None,
    })

    print("\n--- ALARM FLOW RESULT ---")
    print(f"Next Action (from main): {result.get('next_action')}")
    print(f"SOP Guidance: {(result.get('sop_guidance') or 'N/A')[:100]}...")
    print(f"Final Summary: {(result.get('summary') or 'N/A')[:200]}...")
    print()


def test_trace_id_flow():
    """Test Flow 2: User provides trace_id -> triage -> TELEMETRY_TOOL -> reasoning -> diagnosis"""
    print("\n" + "=" * 80)
    print("TEST 2: TRACE_ID FLOW (trace_id -> telemetry fetch -> reasoning -> summary)")
    print("=" * 80 + "\n")

    graph = build_graph()

    trace_telemetry = "Investigating trace: abc-123-def-456"

    result = graph.invoke({
        "messages": [HumanMessage(content="Investigating trace: abc-123-def-456")],
        "telemetry": trace_telemetry,
        "service_name": "payment-service",
        "trace_id": "abc-123-def-456",  # Has trace ID -> TRACE_ID FLOW
        "diagnostic_plan": None,
        "sop_guidance": None,
        "code_analysis": None,
        "reasoning_output": None,
        "next_action": "",
        "summary": None,
        "error": None,
    })

    print("\n--- TRACE_ID FLOW RESULT ---")
    print(f"Trace ID processed: {result.get('trace_id')}")
    print(f"Telemetry fetched: {(result.get('sop_guidance') or 'N/A')[:100]}...")
    print(f"Final Summary: {(result.get('summary') or 'N/A')[:200]}...")
    print()


if __name__ == "__main__":
    try:
        print("\n\n STARTING TRIAGE FLOW TESTS\n")
        test_alarm_flow()
        test_trace_id_flow()
        print("\n ALL TESTS COMPLETED\n")
    except Exception as e:
        print(f"\n TEST ERROR: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
