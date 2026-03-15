from run_sop_agent import run_sop_agent

telemetry = """
    source=prometheus
    job=opentelemetry-collector
    target=${MY_POD_IP}:8888
    scrape_interval=10s
    timestamp_utc=2026-03-05T10:22:30Z

    k8s.namespace.name=observability
    k8s.pod.name=opentelemetry-collector-6f9d7c7b9f-2k9lq
    k8s.node.name=ip-10-0-12-34
    k8s.workload.kind=Deployment
    k8s.workload.name=opentelemetry-collector

    metric.process_resident_memory_bytes=1650000000
    metric.process_virtual_memory_bytes=5120000000
    metric.process_cpu_seconds_total=18342.12

    k8s.container.memory_limit_bytes=2147483648
    k8s.container.memory_request_bytes=419430400

    otel.processor=memory_limiter
    otel.pipeline=traces
    metric.otelcol_processor_refused_spans=0
    metric.otelcol_processor_dropped_spans=0

    otel.exporter=otlp
    metric.otelcol_exporter_send_failed_spans=0
    metric.otelcol_exporter_queue_size=1200
"""

print("Running SOP agent with telemetry")
result = run_sop_agent(telemetry)

print("SOP agent results:\n")
print(result["answer"])