from dotenv import load_dotenv
from src.nodes import run_code_execution_node, run_code_generation_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-04-01T09:15:00Z

    k8s.deployment.name=checkout

    alert=ServiceUnreachable
    alert.message=checkout service is not responding to requests.
    """,
    "service_name": "checkout",
    "sop_guidance": "If a service is unreachable, first verify whether its pods are running and ready.",
    "coding_task": "Check whether the checkout pods are running and ready in the otel-demo namespace. Report the pod name, status, and ready state.",
    "diagnostic_plan": None,
    "reasoning_output": None,
    "generated_code": None,
    "code_execution_history": None,
    "code_analysis": None,
    "root_cause_found": False,
    "next_action": "coding_node",
    "summary": None,
    "error": None,
}

if __name__ == "__main__":
    print("===Running Coding Sub-loop===\n")

    # Step 1: Code Generation produces first script
    state = run_code_generation_node(state)

    # Loop: execute → generate → execute → ... until insight returned
    while state.get("next_action") == "code_execution_node":
        state = run_code_execution_node(state)
        state = run_code_generation_node(state)

    print(f"\n===Final code_analysis returned to Reasoning Agent===\n{state.get('code_analysis')}")
