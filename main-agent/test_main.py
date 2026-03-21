# main-agent/test_main.py
from run_main_agent import run_main_agent

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

if __name__ == "__main__":
    result = run_main_agent(alert=telemetry, service_name="opentelemetry-collector")