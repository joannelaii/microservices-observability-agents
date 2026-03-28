from dotenv import load_dotenv
from src.nodes import run_code_expert_node

load_dotenv()

state = {
    "telemetry": """
    source=prometheus
    timestamp_utc=2026-03-05T10:22:30Z

    k8s.namespace.name=observability
    k8s.pod.name=opentelemetry-collector-6f9d7c7b9f-2k9lq

    metric.process_resident_memory_bytes=1650000000
    k8s.container.memory_limit_bytes=2147483648

    otel.processor=memory_limiter
    metric.otelcol_exporter_queue_size=1200
    """,
    "service_name": "opentelemetry-collector",
    "sop_guidance": "Check memory usage trends. If memory > 80% of limit, inspect queue sizes and consider restarting the collector pod.",
    "coding_task": "Write a Python script that fetches memory usage and exporter queue size over the last 30 minutes and flags if memory exceeds 80% of the container limit.",
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
