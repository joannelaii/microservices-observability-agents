import os, sys
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_main import run_main_agent
from common.backend import llm_and_embeddings

"""
SCORING RUBRIC FOR REASONING NODE TOOL USAGE EVALUATION

This module evaluates how appropriately the reasoning node uses SOP and telemetry tools
based on the input incident context. The scoring rubric assesses:

1. Tool Selection Appropriateness: Did the agent choose the right tools for the incident type?
2. Investigation Sequence: Does the tool call order follow a logical progression (broad→deep)?
3. Query Quality: Are tool arguments specific, relevant, and well-formulated?
4. Iteration Efficiency: Are tool calls necessary or are there redundant/circular patterns?
5. Evidence Sufficiency: Is enough telemetry gathered before reaching a verdict?
6. Verdict Justification: Does the final verdict align with evidence collected?

REQUIRED FIELDS FOR EVALUATION:
- tool_calls_count: Total number of tool invocations (sop vs telemetry)
- sop_call_count: Number of SOP retrieval calls
- telemetry_call_count: Number of telemetry retrieval calls
- tool_call_sequence: List of tool names in order called
- tool_call_args: List of arguments passed to each tool (for query quality assessment)
- incident_type_classification: What incident type was identified (cpu, memory, crash_loop, etc.)
- severity_level: P1, P2, or P3 based on alert
- investigation_scope: Breadth of investigation (namespace-wide, service-specific, trace-level)
- verdict_type: "ROOT_CAUSE_FOUND" or "BEST_EFFORT"
- evidence_types_collected: Which telemetry types were retrieved (metrics, logs, traces)
"""


def fetch_real_test_cases_from_prometheus() -> list:
    """
    Fetch actual alerts from Prometheus and convert them to test cases.
    Falls back to sample test cases if Prometheus is unavailable.
    """
    PROM_ALERTS_URL = "http://localhost:9090/api/v1/alerts"
    ALERT_TO_INCIDENT_TYPE = {
        "FrontendCheckoutErrorRateHigh": "error_rate",
        "FrontendCheckoutFailuresPresent": "error_rate",
        "CheckoutTrafficPresentButFailuresOrSlowness": "checkout-degradation",
        "FrontendTrafficDrop": "traffic",
        "FrontendLatencyHigh": "latency",
        "ServiceRestartDetected": "restart",
        "FrontendOverallErrorRateHigh": "error_rate",
    }

    try:
        response = requests.get(PROM_ALERTS_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        alerts = data.get("data", {}).get("alerts", [])

        test_cases = []
        for alert in alerts:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            alertname = labels.get("alertname", "unknown")
            description = annotations.get(
                "description", annotations.get("summary", "Alert triggered")
            )

            # Extract service name - try multiple fields
            service_name = labels.get("service_name", labels.get("scope", "unknown"))
            if service_name in ("symptom", "unknown"):
                service_name = "frontend"  # Default for symptom alerts

            # Get incident type from the mapping
            incident_type = ALERT_TO_INCIDENT_TYPE.get(alertname, "unknown")

            # Determine severity (map warning to p2, critical to p1, etc.)
            severity_map = {"warning": "p2", "critical": "p1", "info": "p3"}
            severity = labels.get("severity", "warning")
            expected_severity = severity_map.get(severity.lower(), "p3")

            test_case = {
                "telemetry": description,
                "service_name": service_name,
                "expected_issue": alertname,
                "incident_type": incident_type,
                "expected_severity": expected_severity,
            }
            test_cases.append(test_case)

        if test_cases:
            print(f"[INFO] Loaded {len(test_cases)} real test cases from Prometheus")
            return test_cases
        else:
            print("[WARN] No alerts found in Prometheus, using fallback test cases")
            return get_fallback_test_cases()
    except requests.exceptions.ConnectionError:
        print(
            f"[WARN] Cannot connect to Prometheus at {PROM_ALERTS_URL}, using fallback test cases"
        )
        return get_fallback_test_cases()
    except Exception as e:
        print(
            f"[WARN] Error fetching alerts from Prometheus: {e}, using fallback test cases"
        )
        return get_fallback_test_cases()


def get_fallback_test_cases() -> list:
    """Fallback test cases when Prometheus is unavailable."""
    return [
        {
            "telemetry": "Error rate on /api/checkout exceeded 10% for 30s.",
            "service_name": "frontend",
            "expected_issue": "FrontendCheckoutErrorRateHigh",
            "incident_type": "error_rate",
            "expected_severity": "p2",
        },
        {
            "telemetry": "Frontend /api/checkout has active 500 responses.",
            "service_name": "frontend",
            "expected_issue": "FrontendCheckoutFailuresPresent",
            "incident_type": "error_rate",
            "expected_severity": "p2",
        },
        {
            "telemetry": "Active checkout traffic with either elevated failures or latency.",
            "service_name": "frontend",
            "expected_issue": "CheckoutTrafficPresentButFailuresOrSlowness",
            "incident_type": "checkout-degradation",
            "expected_severity": "p2",
        },
        {
            "telemetry": "CPU utilization has been above 85% for the past 10 minutes on the user-service pods.",
            "service_name": "user-service",
            "expected_issue": "HighCPUUtilization",
            "incident_type": "cpu",
            "expected_severity": "p2",
        },
        {
            "telemetry": "Memory usage is at 90% of limit for the order-service pods, causing OOM kills.",
            "service_name": "order-service",
            "expected_issue": "HighMemoryUsage",
            "incident_type": "memory",
            "expected_severity": "p2",
        },
    ]


# Fetch real test cases from Prometheus
test_cases = fetch_real_test_cases_from_prometheus()

# SCORING DIMENSIONS
TOOL_APPROPRIATENESS_MAPPING = {
    "error_rate": {
        "sop_weight": 0.4,
        "telemetry_weight": 0.8,
        "prefer_metrics": True,
        "prefer_logs": True,
    },
    "checkout-degradation": {
        "sop_weight": 0.5,
        "telemetry_weight": 0.9,
        "prefer_metrics": True,
        "prefer_logs": True,
    },
    "traffic": {
        "sop_weight": 0.3,
        "telemetry_weight": 0.8,
        "prefer_metrics": True,
    },
    "latency": {
        "sop_weight": 0.3,
        "telemetry_weight": 0.8,
        "prefer_metrics": True,
        "prefer_traces": True,
    },
    "restart": {
        "sop_weight": 0.4,
        "telemetry_weight": 0.7,
        "prefer_logs": True,
    },
    "cpu": {"sop_weight": 0.3, "telemetry_weight": 0.8, "prefer_metrics": True},
    "memory": {"sop_weight": 0.3, "telemetry_weight": 0.9, "prefer_metrics": True},
    "crash_loop": {
        "sop_weight": 0.4,
        "telemetry_weight": 0.8,
        "prefer_logs": True,
        "prefer_traces": True,
    },
    "database": {
        "sop_weight": 0.5,
        "telemetry_weight": 0.7,
        "prefer_metrics": True,
        "prefer_logs": True,
    },
    "network": {
        "sop_weight": 0.4,
        "telemetry_weight": 0.9,
        "prefer_metrics": True,
        "prefer_traces": True,
    },
}


def judge_diagnosis(telemetry: str, expected_issue: str, summary: str) -> bool:
    """Use LLM as judge to determine if the diagnosis is accurate."""
    llm = llm_and_embeddings()["llm"]

    judge_prompt = f"""
Telemetry: {telemetry}

Expected Issue: {expected_issue}

Agent's Diagnosis Summary: {summary}

Does the agent's diagnosis correctly identify the issue as {expected_issue} based on the telemetry?
Answer with 'Yes' or 'No', followed by a brief explanation (max 50 words).
"""

    try:
        response = llm.invoke(judge_prompt)
        answer = response.content.strip()
        is_correct = answer.lower().startswith("yes")
        return is_correct
    except Exception as e:
        print(f"Error in judging: {e}")
        return False


def score_tool_usage(
    incident_type: str,
    tool_calls_count: int,
    sop_call_count: int,
    telemetry_call_count: int,
    evidence_types_collected: list,
    verdict_type: str,
    expected_severity: str,
) -> dict:
    """
    Score the reasoning node's tool usage appropriateness based on incident type.

    Returns:
        {
            "score": 0-100,
            "appropriateness": 0-100,  # Did it call the right tools?
            "sufficiency": 0-100,      # Did it gather enough evidence?
            "efficiency": 0-100,       # Were calls non-redundant?
            "verdict_alignment": 0-100, # Does verdict match evidence?
            "breakdown": {...}         # Detailed scoring factors
        }
    """
    mapping = TOOL_APPROPRIATENESS_MAPPING.get(incident_type, {})

    # Appropriateness: Check if tool distribution matches incident type
    appropriateness = 100
    if sop_call_count == 0 and mapping.get("sop_weight", 0) > 0.3:
        appropriateness -= 20  # Should have checked SOP for this incident type
    if telemetry_call_count == 0 and mapping.get("telemetry_weight", 0) > 0.7:
        appropriateness -= 30  # Should have gathered telemetry for this incident type

    # Sufficiency: Check evidence types collected vs expected
    sufficiency = 50  # baseline
    expected_evidence = []
    if mapping.get("prefer_metrics"):
        expected_evidence.append("metrics")
    if mapping.get("prefer_logs"):
        expected_evidence.append("logs")
    if mapping.get("prefer_traces"):
        expected_evidence.append("traces")

    for evidence_type in expected_evidence:
        if evidence_type in evidence_types_collected:
            sufficiency += 20

    if verdict_type == "ROOT_CAUSE_FOUND":
        sufficiency += 10

    # Efficiency: Penalize excessive tool calls
    efficiency = 100
    max_efficient_calls = 4
    if tool_calls_count > max_efficient_calls:
        efficiency -= (tool_calls_count - max_efficient_calls) * 5
    efficiency = max(10, efficiency)  # Floor at 10

    # Verdict alignment: Strong verdicts require more evidence
    verdict_alignment = 100
    if verdict_type == "ROOT_CAUSE_FOUND" and tool_calls_count < 2:
        verdict_alignment = 40  # Not enough investigation for definitive verdict
    elif verdict_type == "BEST_EFFORT" and tool_calls_count == 0:
        verdict_alignment = 20  # Should have tried at least one tool

    # Severity-based expectations
    if expected_severity == "p1" and verdict_type == "BEST_EFFORT":
        verdict_alignment -= (
            10  # P1 incidents should have more definitive investigation
        )

    # Calculate overall score (weighted average)
    overall_score = (
        appropriateness * 0.25
        + sufficiency * 0.30
        + efficiency * 0.25
        + verdict_alignment * 0.20
    )

    return {
        "score": min(100, max(0, overall_score)),
        "appropriateness": appropriateness,
        "sufficiency": sufficiency,
        "efficiency": efficiency,
        "verdict_alignment": verdict_alignment,
        "breakdown": {
            "tool_calls_count": tool_calls_count,
            "sop_calls": sop_call_count,
            "telemetry_calls": telemetry_call_count,
            "evidence_types": evidence_types_collected,
            "verdict": verdict_type,
        },
    }


def extract_tool_usage_metrics(result: dict) -> dict:
    """
    Extract tool usage metrics from agent result for scoring.

    REQUIRED OUTPUT FIELDS FROM AGENT:
    - reasoning_output: The verdict and investigation narrative
    - tool_calls_executed: [{"tool": "sop"|"telemetry", "args": {...}, "result": {...}}]
    - evidence_collected: ["metrics", "logs", "traces", ...]
    - verdict_type: "ROOT_CAUSE_FOUND" or "BEST_EFFORT"
    """
    # This would be populated by instrumenting the reasoning node
    # to track tool calls during execution
    return {
        "tool_calls_count": 0,
        "sop_call_count": 0,
        "telemetry_call_count": 0,
        "evidence_types_collected": [],
        "verdict_type": "BEST_EFFORT",
    }


def run_tests():
    """
    Run the LLM judge tests on the agentic system.

    Evaluates both:
    1. Diagnosis accuracy (does output correctly identify the issue?)
    2. Tool usage appropriateness (did reasoning node use tools efficiently?)
    """
    results = []

    for i, test_case in enumerate(test_cases):
        print(f"\nRunning test case {i + 1}: {test_case['expected_issue']}")
        print(f"  Service: {test_case['service_name']}")
        print(f"  Expected Incident Type: {test_case.get('incident_type', 'unknown')}")

        try:
            result = run_main_agent(test_case["telemetry"], test_case["service_name"])
            summary = result.get("summary", "")
            reasoning_output = result.get("reasoning_output", "")
            error = result.get("error", "")

            if error:
                print(f"  Agent error: {error}")
                is_correct = False
                tool_score = 0
            else:
                # Diagnosis correctness
                is_correct = judge_diagnosis(
                    test_case["telemetry"], test_case["expected_issue"], summary
                )

                # Tool usage scoring (requires instrumentation)
                # TODO: Instrument reasoning_node to populate tool metrics
                tool_metrics = extract_tool_usage_metrics(result)
                tool_score_dict = score_tool_usage(
                    incident_type=test_case.get("incident_type", "unknown"),
                    tool_calls_count=tool_metrics["tool_calls_count"],
                    sop_call_count=tool_metrics["sop_call_count"],
                    telemetry_call_count=tool_metrics["telemetry_call_count"],
                    evidence_types_collected=tool_metrics["evidence_types_collected"],
                    verdict_type=tool_metrics["verdict_type"],
                    expected_severity=test_case.get("expected_severity", "p3"),
                )
                tool_score = tool_score_dict["score"]

            results.append(
                {
                    "test_case": i + 1,
                    "expected": test_case["expected_issue"],
                    "incident_type": test_case.get("incident_type", "unknown"),
                    "severity": test_case.get("expected_severity", "p3"),
                    "diagnosis_correct": is_correct,
                    "tool_usage_score": tool_score,
                    "summary": summary,
                    "reasoning": reasoning_output[:200] if reasoning_output else "N/A",
                }
            )

            print(f"  ✓ Diagnosis Correct: {is_correct}")
            print(f"  ✓ Tool Usage Score: {tool_score:.1f}/100")

        except Exception as e:
            print(f"  ✗ Error running test case {i + 1}: {e}")
            results.append(
                {
                    "test_case": i + 1,
                    "expected": test_case["expected_issue"],
                    "incident_type": test_case.get("incident_type", "unknown"),
                    "severity": test_case.get("expected_severity", "p3"),
                    "diagnosis_correct": False,
                    "tool_usage_score": 0,
                    "summary": str(e),
                    "reasoning": "",
                }
            )

    # Calculate metrics
    correct_count = sum(1 for r in results if r["diagnosis_correct"])
    total_count = len(results)
    accuracy = correct_count / total_count if total_count > 0 else 0
    avg_tool_score = (
        sum(r["tool_usage_score"] for r in results) / total_count
        if total_count > 0
        else 0
    )

    print(f"\n{'=' * 60}")
    print(f"TEST RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Diagnosis Accuracy: {accuracy:.2%} ({correct_count}/{total_count})")
    print(f"Avg Tool Usage Score: {avg_tool_score:.1f}/100")
    print(f"{'=' * 60}\n")

    for r in results:
        status = "✓ PASS" if r["diagnosis_correct"] else "✗ FAIL"
        print(
            f"Test {r['test_case']:2d}: {status} | {r['incident_type']:12s} [{r['severity']}] | Tool Score: {r['tool_usage_score']:5.1f}"
        )
        print(f"         Expected: {r['expected']}")
        if r["tool_usage_score"] == 0 and not r["diagnosis_correct"]:
            print(f"         Error: {r['summary'][:80]}")


if __name__ == "__main__":
    run_tests()
