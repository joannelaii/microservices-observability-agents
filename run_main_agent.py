import os
from src.graph import build_graph
# from src import run_main_agent as run_main_agent_func

def run_main_agent(alert: str, service_name: str):
    """Entrypoint used by test_main.py and external callers."""

    graph = build_graph()
    return graph.invoke({
        "telemetry": alert,
        "service_name": service_name,
        "coding_task": None,
        "sop_guidance": None,
        "code_analysis": None,
        "reasoning_output": None,
        "summary": None,
        "error": None,
    })