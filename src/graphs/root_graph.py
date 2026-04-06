from langgraph.graph import StateGraph, START, END

from .triage_graph import build_triage_graph
from .reasoning_graph import build_reasoning_graph
from common.state import DiagnosticState
from nodes.synthesis import run_synthesis_node
from nodes.nodes import run_coding_agent_node
from nodes.summariser import run_summariser_node

MAIN_NODE = "main_node"
SUMMARIZER_NODE = "summarizer"
TRIAGE = "triage"
REASONING= "reasoning"
CODING_NODE = "coding_node"
SYNTHESIS_NODE = "synthesis"


def build_graph():
    graph = StateGraph(DiagnosticState)
    triage_graph = build_triage_graph()
    reasoning_graph = build_reasoning_graph()

    # nodes
    graph.add_node(TRIAGE, triage_graph)
    graph.add_node(REASONING, reasoning_graph)
    graph.add_node(CODING_NODE, run_coding_agent_node)
    graph.add_node(SYNTHESIS_NODE, run_synthesis_node)
    graph.add_node(SUMMARIZER_NODE, run_summariser_node)

    graph.add_edge(START, TRIAGE)
    graph.add_edge(TRIAGE, REASONING)
    graph.add_edge(REASONING, CODING_NODE)
    graph.add_edge(CODING_NODE, REASONING)
    graph.add_edge(REASONING, SYNTHESIS_NODE)
    graph.add_edge(SYNTHESIS_NODE, SUMMARIZER_NODE)
    graph.add_edge(SUMMARIZER_NODE, END)

    return graph.compile()
