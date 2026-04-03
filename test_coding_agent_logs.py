from dotenv import load_dotenv
from src.nodes import run_code_expert_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-04-01T09:15:00Z

    k8s.deployment.name=checkout

    metric.http_errors_total=891
    metric.pod_restarts=5

    alert=HighErrorRate
    alert.message=checkout service is returning errors with repeated pod restarts detected.
    """,
    "service_name": "checkout",
    "sop_guidance": "If a service shows elevated errors or restarts, fetch recent pod logs and scan for ERROR, exception, or panic lines to identify the root cause.",
    "coding_task": "Fetch the last 100 log lines from the checkout pod and scan for ERROR, exception, panic, or timeout patterns. Report what errors are present and how frequently they appear.",
    "diagnostic_plan": None,
    "reasoning_output": None,
    "code_analysis": None,
    "root_cause_found": False,
    "next_action": "coding_node",
    "summary": None,
    "error": None,
}

if __name__ == "__main__":
    print("===Running Code Agent Node===\n")
    result = run_code_expert_node(state)
