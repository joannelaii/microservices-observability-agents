from langgraph.graph import StateGraph, START
from common.state import DiagnosticState
from nodes.triage import run_main_agent_node, triage_node

MAIN_NODE = "main_node"
TRIAGE_NODE = "triage_node"

def build_triage_graph():
    triage_graph = StateGraph(DiagnosticState)
    triage_graph.add_node(MAIN_NODE, run_main_agent_node)
    triage_graph.add_node(TRIAGE_NODE, triage_node)
    triage_graph.add_edge(START, MAIN_NODE)
    triage_graph.add_edge(MAIN_NODE, TRIAGE_NODE)
    triage_graph = triage_graph.compile()
    return triage_graph