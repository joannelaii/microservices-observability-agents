import os
from dotenv import load_dotenv

from sop_agent.graph import build_sop_graph

load_dotenv()


def run_sop_agent(telemetry: str, sop_dir: str | None = None):
    graph = build_sop_graph(sop_dir)
    result = graph.invoke(
        {
            "telemetry": telemetry,
            "retrieved_sops": [],
            "answer": "",
        },
    )
    return result
