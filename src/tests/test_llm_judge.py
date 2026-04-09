import os, sys


# Add parent directory to path for imports
if __package__ in (None, ""):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src_dir = os.path.join(repo_root, "src")
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

from dotenv import load_dotenv

load_dotenv()
from langchain_openai import ChatOpenAI
import requests
from datetime import datetime, timezone
import time

from langchain_core.messages import AIMessage, HumanMessage
from common.state import DiagnosticState
from src.main import (
    _payload_to_alert_context,
    _get_graph,
    build_incident_payload,
    fetch_alerts,
    incident_key,
)

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
    ALERT_TO_INCIDENT_TYPE = {
        "FrontendCheckoutErrorRateHigh": "error_rate",
        "FrontendCheckoutFailuresPresent": "error_rate",
        "CheckoutTrafficPresentButFailuresOrSlowness": "checkout-degradation",
        "FrontendTrafficDrop": "traffic",
        "FrontendLatencyHigh": "latency",
        "ServiceRestartDetected": "restart",
        "FrontendOverallErrorRateHigh": "error_rate",
        "AdServiceCpuHighWithLatencyRegression": "cpu",
        "CartEmptyCartErrorsPresent": "error_rate",
    }

    alerts = fetch_alerts()

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
            "alert": alert,
            "telemetry": description,
            "service_name": service_name,
            "expected_issue": alertname,
            "incident_type": incident_type,
            "expected_severity": expected_severity,
        }
        test_cases.append(test_case)

    print(f"[INFO] Loaded {len(test_cases)} real test cases from Prometheus")
    return test_cases


# Fetch real test cases from Prometheus
test_cases = fetch_real_test_cases_from_prometheus()
# test_cases = get_fallback_test_cases()

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
    "kafka": {
        "sop_weight": 0.5,
        "telemetry_weight": 0.8,
        "prefer_metrics": True,
        "prefer_logs": True,
    },
}


def judge_diagnosis(telemetry: str, expected_issue: str, summary: str) -> bool:
    """Use LLM as judge to determine if the diagnosis is accurate."""
    llm = ChatOpenAI(model="gpt-5.4-mini", temperature=0)

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
        print("Answer is", answer)
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

    # Track deductions for transparency
    deductions = []

    # Appropriateness: Check if tool distribution matches incident type
    appropriateness = 100
    if sop_call_count == 0 and mapping.get("sop_weight", 0) > 0.3:
        appropriateness -= 20  # Should have checked SOP for this incident type
        deductions.append({"reason": "Missing SOP calls", "amount": -20})
    if telemetry_call_count == 0 and mapping.get("telemetry_weight", 0) > 0.7:
        appropriateness -= 30  # Should have gathered telemetry for this incident type
        deductions.append({"reason": "Missing telemetry calls", "amount": -30})

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
        excess_calls = tool_calls_count - max_efficient_calls
        efficiency_penalty = excess_calls * 5
        efficiency -= efficiency_penalty
        deductions.append(
            {
                "reason": f"Efficiency penalty ({excess_calls} excess calls)",
                "amount": -efficiency_penalty,
            }
        )
    efficiency = max(10, efficiency)  # Floor at 10

    # Verdict alignment: Strong verdicts require more evidence
    verdict_alignment = 100
    if verdict_type == "ROOT_CAUSE_FOUND" and tool_calls_count < 2:
        verdict_alignment = 40  # Not enough investigation for definitive verdict
        deductions.append(
            {"reason": "Strong verdict without sufficient investigation", "amount": -60}
        )
    elif verdict_type == "BEST_EFFORT" and tool_calls_count == 0:
        verdict_alignment = 20  # Should have tried at least one tool
        deductions.append({"reason": "No investigation attempted", "amount": -80})

    # Severity-based expectations
    if expected_severity == "p1" and verdict_type == "BEST_EFFORT":
        verdict_alignment -= (
            10  # P1 incidents should have more definitive investigation
        )
        deductions.append(
            {"reason": "P1 severity with low confidence verdict", "amount": -10}
        )

    # Total score is the sum of weighted component scores.
    overall_score = sum(
        [
            appropriateness * 0.25,
            sufficiency * 0.30,
            efficiency * 0.25,
            verdict_alignment * 0.20,
        ]
    )

    return {
        "score": min(100, max(0, overall_score)),
        "appropriateness": appropriateness,
        "sufficiency": sufficiency,
        "efficiency": efficiency,
        "verdict_alignment": verdict_alignment,
        "deductions": deductions,
        "breakdown": {
            "appropriateness_score": appropriateness,
            "sufficiency_score": sufficiency,
            "efficiency_score": efficiency,
            "verdict_alignment_score": verdict_alignment,
            "component_contributions": {
                "appropriateness": appropriateness * 0.25,
                "sufficiency": sufficiency * 0.30,
                "efficiency": efficiency * 0.25,
                "verdict_alignment": verdict_alignment * 0.20,
            },
            "tool_calls_count": tool_calls_count,
            "sop_calls": sop_call_count,
            "telemetry_calls": telemetry_call_count,
            "evidence_types": evidence_types_collected,
            "verdict": verdict_type,
            "deductions": deductions,
        },
    }


def extract_tool_usage_metrics(result: dict) -> dict:
    """
    Extract tool usage metrics from agent result for scoring.

    DERIVED FIELDS:
    - reasoning_output: The verdict and investigation narrative
    - evidence_collected: Derived from summary.evidence if available
    - verdict_type: Derived from root_cause_found ("ROOT_CAUSE_FOUND" if True, else "BEST_EFFORT")
    """
    reasoning_messages = result.get("reasoning_messages", [])

    tool_calls_count = 0
    sop_call_count = 0
    telemetry_call_count = 0

    for msg in reasoning_messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name")
                if tool_name == "retrieve_sop":
                    sop_call_count += 1
                elif tool_name == "get_relevant_telemetry":
                    telemetry_call_count += 1
                tool_calls_count += 1

    # Derive evidence_types_collected from summary.evidence
    summary = result.get("summary")
    if summary and hasattr(summary, "evidence"):
        evidence_types_collected = summary.evidence
    else:
        evidence_types_collected = []

    # Derive verdict_type from root_cause_found
    verdict_type = (
        "ROOT_CAUSE_FOUND" if result.get("root_cause_found", False) else "BEST_EFFORT"
    )

    return {
        "tool_calls_count": tool_calls_count,
        "sop_call_count": sop_call_count,
        "telemetry_call_count": telemetry_call_count,
        "evidence_types_collected": evidence_types_collected,
        "verdict_type": verdict_type,
    }


def format_tool_score_receipt(tool_score: dict, tool_metrics: dict) -> str:
    breakdown = tool_score.get("breakdown", {})
    contributions = breakdown.get("component_contributions", {})
    evidence_types = breakdown.get("evidence_types", [])
    deductions = breakdown.get("deductions", [])

    lines = [
        f"         Tool Usage Score: {tool_score['score']:.1f}/100",
        "         Breakdown:",
        f"           Appropriateness   : {breakdown.get('appropriateness_score', 0):.1f}",
        f"           Sufficiency       : {breakdown.get('sufficiency_score', 0):.1f}",
        f"           Efficiency        : {breakdown.get('efficiency_score', 0):.1f}",
        f"           Certainty penalty : {breakdown.get('verdict_alignment_score', 0):.1f}",
    ]

    if contributions:
        lines.append("         Weighted Contributions:")
        for name, value in contributions.items():
            label = name.replace("_", " ").capitalize()
            lines.append(f"           {label:<15}: {value:.1f}")

    if deductions:
        lines.append("         Deductions Applied:")
        for deduction in deductions:
            reason = deduction.get("reason", "Unknown")
            amount = deduction.get("amount", 0)
            lines.append(f"           {reason:<40}: {amount}")

    lines.extend(
        [
            "         Tool Metrics:",
            f"           Calls      : {tool_metrics.get('tool_calls_count', 0)}",
            f"           SOP        : {tool_metrics.get('sop_call_count', 0)}",
            f"           Telemetry  : {tool_metrics.get('telemetry_call_count', 0)}",
            f"           Evidence   : {evidence_types if evidence_types else 'None'}",
            f"           Verdict    : {breakdown.get('verdict', tool_metrics.get('verdict_type', ''))}",
        ]
    )

    return "\n".join(lines)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_tests():
    """
    Run the LLM judge tests on the agentic system for Kafka issue detection.

    Evaluates diagnosis accuracy over multiple calls.
    """
    results = []

    # Use the single test case
    test_case = [a for a in test_cases if a["alert"].get("state") == "firing"][0]
    payload = build_incident_payload(
        incident_key(test_case["alert"]), [test_case["alert"]]
    )
    total_times = 10

    print(f"Running test for Kafka issue detection")
    print(f"  Service: {test_case['service_name']}")
    print(f"  Expected Incident Type: {test_case.get('incident_type', 'unknown')}")
    print(f"  Running {total_times} times to measure accuracy...")

    for i in range(total_times):
        print(f"  Run {i + 1}/{total_times}")
        try:
            graph = _get_graph()
            alert_context = _payload_to_alert_context(payload)
            service_name = payload.get("service_name") or "opentelemetry-collector"

            started = time.perf_counter()
            result: DiagnosticState = graph.invoke(
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
            duration = time.perf_counter() - started
            root_cause_found = result["root_cause_found"]
            total_tokens = result.get("meta_total_tokens", 0)

            summary_obj = result.get("summary")
            if summary_obj is None:
                raise ValueError("Summariser did not return a Diagnosis object.")
            summary = summary_obj.incident.summary
            reasoning_output = result.get("reasoning_output", "")
            error = result.get("error", "")

            if error:
                print(f"    Agent error: {error}")
                is_correct = False
            else:
                # Diagnosis correctness
                is_correct = judge_diagnosis(
                    test_case["telemetry"], test_case["expected_issue"], summary
                )

            # Tool usage scoring
            tool_metrics = extract_tool_usage_metrics(result)
            tool_score = score_tool_usage(
                test_case.get("incident_type", "unknown"),
                tool_metrics["tool_calls_count"],
                tool_metrics["sop_call_count"],
                tool_metrics["telemetry_call_count"],
                tool_metrics["evidence_types_collected"],
                tool_metrics["verdict_type"],
                test_case.get("expected_severity", "p3"),
            )

            results.append(
                {
                    "run": i + 1,
                    "expected": test_case["expected_issue"],
                    "incident_type": test_case.get("incident_type", "unknown"),
                    "severity": test_case.get("expected_severity", "p3"),
                    "diagnosis_correct": is_correct,
                    "summary": summary,
                    "reasoning": reasoning_output[:200] if reasoning_output else "N/A",
                    "root_cause_found": root_cause_found,
                    "duration": duration,
                    "total_tokens": total_tokens,
                    "tool_score": tool_score,
                    "tool_metrics": tool_metrics,
                    "tool_total_score": tool_score.get("score", 0),
                    "appropriateness": tool_score.get("appropriateness", 0),
                    "sufficiency": tool_score.get("sufficiency", 0),
                    "efficiency": tool_score.get("efficiency", 0),
                    "verdict_alignment": tool_score.get("verdict_alignment", 0),
                }
            )

            print(f"    ✓ Diagnosis Correct: {is_correct}")

        except Exception as e:
            print(f"    ✗ Error in run {i + 1}: {e}")
            results.append(
                {
                    "run": i + 1,
                    "expected": test_case["expected_issue"],
                    "incident_type": test_case.get("incident_type", "unknown"),
                    "severity": test_case.get("expected_severity", "p3"),
                    "diagnosis_correct": False,
                    "summary": str(e),
                    "reasoning": "",
                    "root_cause_found": False,
                    "duration": 0,
                    "total_tokens": 0,
                    "tool_score": {"score": 0},
                    "tool_metrics": {
                        "tool_calls_count": 0,
                        "sop_call_count": 0,
                        "telemetry_call_count": 0,
                        "evidence_types_collected": [],
                        "verdict_type": "N/A",
                    },
                    "tool_total_score": 0,
                    "appropriateness": 0,
                    "sufficiency": 0,
                    "efficiency": 0,
                    "verdict_alignment": 0,
                }
            )

    # Calculate metrics
    correct_count = sum(
        1 for r in results if r["diagnosis_correct"] and r["root_cause_found"]
    )
    total_count = len(results)
    accuracy = correct_count / total_count if total_count > 0 else 0
    avg_duration = _mean([r["duration"] for r in results])
    avg_total_tokens = _mean([r["total_tokens"] for r in results])
    avg_total_score = _mean([r["tool_total_score"] for r in results])
    avg_appropriateness = _mean([r["appropriateness"] for r in results])
    avg_sufficiency = _mean([r["sufficiency"] for r in results])
    avg_efficiency = _mean([r["efficiency"] for r in results])
    avg_verdict_alignment = _mean([r["verdict_alignment"] for r in results])

    verdict_counts = {}
    for r in results:
        verdict = r.get("tool_metrics", {}).get("verdict_type", "N/A")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"TEST RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Diagnosis Accuracy: {accuracy:.2%} ({correct_count}/{total_count})")
    print(f"Average Duration: {avg_duration:.2f} s")
    print(f"Average Total Tokens: {avg_total_tokens:.1f}")
    print(f"Average Total Score: {avg_total_score:.1f}/100")
    print(f"Average Appropriateness: {avg_appropriateness:.1f}")
    print(f"Average Sufficiency: {avg_sufficiency:.1f}")
    print(f"Average Efficiency: {avg_efficiency:.1f}")
    print(f"Average Verdict Alignment: {avg_verdict_alignment:.1f}")
    if verdict_counts:
        verdict_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(verdict_counts.items())
        )
        print(f"Verdict Distribution: {verdict_summary}")
    print(f"{'=' * 60}\n")

    # Aggregate deductions across all test runs
    deductions_counter = {}
    for r in results:
        tool_score = r.get("tool_score", {})
        deductions = tool_score.get("deductions", [])
        for deduction in deductions:
            reason = deduction.get("reason", "Unknown")
            amount = deduction.get("amount", 0)
            if reason not in deductions_counter:
                deductions_counter[reason] = {"count": 0, "total": 0}
            deductions_counter[reason]["count"] += 1
            deductions_counter[reason]["total"] += amount

    # Print aggregated deductions report
    if deductions_counter:
        print("DEDUCTION ANALYSIS ACROSS ALL RUNS")
        print(f"{'-' * 60}")
        for reason, stats in sorted(deductions_counter.items()):
            count = stats["count"]
            total = stats["total"]
            print(f"  {reason:<45}: {count:2d}x ({total:4d} pts total)")
        print(f"{'-' * 60}\n")

    for r in results:
        status = (
            "✓ PASS" if r["diagnosis_correct"] and r["root_cause_found"] else "✗ FAIL"
        )
        print(
            f"Run {r['run']:2d}: {status} | {r['incident_type']:12s} [{r['severity']}]"
        )
        print(f"         Alert name: {r['expected']}")
        if not r["diagnosis_correct"]:
            print(f"         Summary: {r['summary']}")
        else:
            print(f"         Duration: {r['duration']:.2f} s")
            print(f"         Total Tokens: {r['total_tokens']}")
            print(format_tool_score_receipt(r["tool_score"], r["tool_metrics"]))
            print(f"         Verdict Type: {r['tool_metrics']['verdict_type']}")


if __name__ == "__main__":
    run_tests()
