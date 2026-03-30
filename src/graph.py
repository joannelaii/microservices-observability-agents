from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from src.tools.sop import retrieve_sop
from src.tools.telemetry import get_relevant_telemetry
from .state import DiagnosticState
from .nodes import (
    run_best_effort_node,
    run_main_agent_node,
    run_code_expert_node,
    run_reasoning_node,
    run_summariser_node,
    triage_node,
)

MAIN_NODE = "main_node"
SUMMARIZER_NODE = "summarizer_node"
TRIAGE_NODE = "triage_node"
REASONING_NODE = "reasoning_node"
CODING_NODE = "coding_node"
SOP_TOOL = "sop_tool"
TELEMETRY_TOOL = "telemetry_tool"
# DIAGNOSIS = "synthesize_diagnosis"
BEST_EFFORT = "synthesize_best_effort"


def route_next(state: DiagnosticState) -> str:
    action = state["next_action"]

    if action in [CODING_NODE, TELEMETRY_TOOL, BEST_EFFORT]:
        return action

    raise ValueError("action not found")


def build_graph():
    graph = StateGraph(DiagnosticState)

    # add tool nodes
    graph.add_node(SOP_TOOL, ToolNode([retrieve_sop]))
    graph.add_node(TELEMETRY_TOOL, ToolNode([get_relevant_telemetry]))

    # Add nodes
    graph.add_node(MAIN_NODE, run_main_agent_node)
    # TODO: write triage_node function
    graph.add_node(TRIAGE_NODE, triage_node)
    graph.add_node(REASONING_NODE, run_reasoning_node)
    graph.add_node(CODING_NODE, run_code_expert_node)
    graph.add_node(BEST_EFFORT, run_best_effort_node)
    graph.add_node(SUMMARIZER_NODE, run_summariser_node)

    # Adjust flow accordingly
    graph.add_edge(START, MAIN_NODE)
    # TODO: add triage edge between MAIN_NODE and SOP_TOOL
    graph.add_edge(MAIN_NODE, TRIAGE_NODE)
    # Triage always routes to SOP_TOOL (rule-based severity classification handled by triage_node)
    graph.add_edge(TRIAGE_NODE, SOP_TOOL)
    # Both SOP and telemetry feed into reasoning
    graph.add_edge(SOP_TOOL, REASONING_NODE)
    graph.add_edge(TELEMETRY_TOOL, REASONING_NODE)
    # Conditional routing from reasoning (code expert, telemetry, or diagnosis)
    graph.add_conditional_edges(REASONING_NODE, route_next)

    # loop nodes
    graph.add_edge(CODING_NODE, REASONING_NODE)

    # ending nodes
    graph.add_edge(BEST_EFFORT, SUMMARIZER_NODE)
    graph.add_edge(SUMMARIZER_NODE, END)

    return graph.compile()
