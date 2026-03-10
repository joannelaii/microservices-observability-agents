from dotenv import load_dotenv

from src.graph import build_reasoning_graph

load_dotenv()

# ------------------------------------------------------------------
# Isolated unit test for the reasoning agent.
#
# Purpose: verify that the graph compiles, all three nodes execute
# in order, state is passed correctly, and the LLM calls succeed.
#
# sop_output and code_output are both None here — in production
# these are supplied by the main orchestrator after the SOP agent
# and Code agent have run. This test exercises the reasoning agent
# in isolation without pretending to have their outputs.
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("Building reasoning agent graph...")
    graph = build_reasoning_graph()
    print("Graph built. Invoking with telemetry only (no SOP or Code agent output)...\n")

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

    result = graph.invoke(
        {
            "telemetry": telemetry,
            "sop_output": None,           # not available — supplied by orchestrator in production
            "code_output": None,          # not available — supplied by orchestrator in production
            "signal_classification": "",
            "hypotheses": "",
            "causal_chains": "",
            "telemetry_gaps": "",
            "reasoning_summary": "",
        }
    )

    print("=== NODE OUTPUTS ===\n")
    print("-- signal_classification --")
    print(result["signal_classification"])
    print("\n-- hypotheses --")
    print(result["hypotheses"])
    print("\n-- causal_chains --")
    print(result["causal_chains"])
    print("\n-- telemetry_gaps --")
    print(result["telemetry_gaps"])
    print("\n=== FINAL REASONING SUMMARY ===\n")
    print(result["reasoning_summary"])