from src.nodes.nodes import run_reasoning_node

initial_state = {
    "telemetry": "High error rate observed at 2026-03-29T14:00:00Z, window 13:55Z to 14:05Z",
    "service_name": "PaymentService",
    "sop_content": """
## TRIGGERS
- Error rate > 5% sustained for 5 minutes
- Latency p95 > 2000ms

## CHECKS
- Check error rate for payment-service in Prometheus
- Check for timeout or exception logs in Loki
- Check recent pod restarts

## MITIGATION
- Scale up payment-service replicas
- Check downstream database connectivity
    """,
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