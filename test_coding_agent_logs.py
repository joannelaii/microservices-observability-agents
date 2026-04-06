from dotenv import load_dotenv
from src.nodes import run_code_execution_node, run_code_generation_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-04-06T09:15:00Z

    k8s.deployment.name=email
    k8s.pod.name=email-7589776695-m9c8b

    alert=HighErrorRate
    alert.message=email service is returning errors with repeated pod restarts detected.
    """,
    "service_name": "email",
    "sop_guidance": "If a service shows elevated errors or restarts, fetch recent pod logs and scan for ERROR, exception, or panic lines to identify the root cause.",
    "coding_task": "Fetch the last 100 log lines from pod email-7589776695-m9c8b and scan for ERROR, exception, panic, or timeout patterns. Report what errors are present and how frequently they appear.",
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

    state = run_code_generation_node(state)

    while state.get("next_action") == "code_execution_node":
        state = run_code_execution_node(state)
        state = run_code_generation_node(state)

    print(f"\n===Final code_analysis returned to Reasoning Agent===\n{state.get('code_analysis')}")
