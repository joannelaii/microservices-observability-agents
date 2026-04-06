from dotenv import load_dotenv
from src.nodes import run_coding_agent_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-04-06T09:15:00Z

    k8s.deployment.name=email
    k8s.pod.name=email-6d89bb6d76-26hs2

    alert=ServiceUnreachable
    alert.message=email service is not responding to requests.
    """,
    "service_name": "email",
    "sop_guidance": "If a service is unreachable, first verify whether its pods are running and ready.",
    "coding_task": "Check whether pod email-6d89bb6d76-26hs2 is running and ready in the otel-demo namespace. Report the pod status and ready state.",
    "diagnostic_plan": None,
    "reasoning_output": None,
    "code_analysis": None,
    "root_cause_found": False,
    "next_action": "coding_node",
    "summary": None,
    "error": None,
}

if __name__ == "__main__":
    print("===Running Diagnostic Agent===\n")
    state = run_coding_agent_node(state)
    print(f"\n===Final code_analysis returned to Reasoning Agent===\n{state.get('code_analysis')}")
