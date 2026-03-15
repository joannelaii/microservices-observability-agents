import os
from dotenv import load_dotenv

from sop_agent.graph import build_sop_graph

def run_sop_agent(telemetry: str, sop_dir: str | None = None) -> dict:
    load_dotenv()

    if sop_dir is None:
        sop_dir = os.path.join(os.path.dirname(__file__), "..", "sops")
        sop_dir = os.path.abspath(sop_dir)

    graph = build_sop_graph(sop_dir)
    result = graph.invoke(
        {
            "telemetry": telemetry,
            "retrieved_sops": [],
            "answer": "",
        }
    )
    return result