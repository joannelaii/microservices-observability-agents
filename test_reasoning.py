from pathlib import Path
from src.nodes import run_reasoning_node

sop_path = Path("src/sops/trace_telemetry.md")

sop_text = sop_path.read_text(encoding="utf-8")

initial_state = {
    "telemetry": "High error rate observed at 2026-04-04T23:29:30.669Z",
    "service_name": "checkout",
    "sop_content": sop_text,
    "sop_guidance": None,
    "diagnostic_plan": None,
    "code_analysis": None,
    "reasoning_output": None,
    "root_cause_found": False,
    "next_action": "",
    "best_effort": None,
    "summary": None,
    "error": None,
}

result = run_reasoning_node(initial_state)

print("\n========== REASONING RESULT ==========")
print(f"Next action:      {result['next_action']}")
print(f"Root cause found: {result['root_cause_found']}")
print(f"\nReasoning output:\n{result['reasoning_output']}")