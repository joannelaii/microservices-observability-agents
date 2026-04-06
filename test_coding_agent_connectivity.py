from dotenv import load_dotenv
from src.nodes import run_coding_agent_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-04-06T09:15:00Z

    k8s.deployment.name=checkout
    k8s.pod.name=checkout-6bdc6bf878-qpdff

    alert=DependencyUnreachable
    alert.message=checkout service is failing to reach downstream dependencies.
    """,
    "service_name": "checkout",
    "sop_guidance": "If a service cannot reach its dependencies, verify DNS resolution and HTTP connectivity to each downstream service from within the affected pod.",
    "coding_task": "From within pod checkout-6bdc6bf878-qpdff, first retrieve its environment variables to discover downstream dependency addresses, then check network connectivity to each. Report whether each dependency is reachable.",
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
