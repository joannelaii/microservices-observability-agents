from langgraph.graph import StateGraph, START
from common.state import DiagnosticState
from nodes.triage import run_incident_builder_agent_node, triage_node

INCIDENT_BUILDER_NODE = "incident_builder_node"
TRIAGE_NODE = "triage_node"

def build_triage_graph():
    triage_graph = StateGraph(DiagnosticState)
    triage_graph.add_node(INCIDENT_BUILDER_NODE, run_incident_builder_agent_node)
    triage_graph.add_node(TRIAGE_NODE, triage_node)
    triage_graph.add_edge(START, INCIDENT_BUILDER_NODE)
    triage_graph.add_edge(INCIDENT_BUILDER_NODE, TRIAGE_NODE)
    triage_graph = triage_graph.compile()
    return triage_graph