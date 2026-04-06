from graphs.root_graph import build_graph


telemetry = """
source=prometheus
timestamp_utc=2026-03-05T10:22:30Z

k8s.namespace.name=observability
k8s.pod.name=opentelemetry-collector-6f9d7c7b9f-2k9lq

metric.process_resident_memory_bytes=1650000000
k8s.container.memory_limit_bytes=2147483648

otel.processor=memory_limiter
metric.otelcol_exporter_queue_size=1200
"""


def run_main_agent(alert: str, service_name: str):
    """Entrypoint used by test_main.py and external callers."""
    graph = build_graph()
    return graph.invoke({
        "telemetry": alert,
        "service_name": service_name,
        "start_time": None,
        "sop_guidance": None,
        "code_analysis": None,
        "reasoning_output": None,
        "summary": None,
        "error": None,
    })


if __name__ == "__main__":
    result = run_main_agent(alert=telemetry, service_name="opentelemetry-collector")