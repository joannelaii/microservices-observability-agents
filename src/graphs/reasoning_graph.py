from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from common.state import DiagnosticState
from nodes.reasoning import run_reasoning_node
from nodes.nodes import run_code_expert_node
from tools.sop import retrieve_sop
from tools.telemetry import get_relevant_telemetry

REASONING_NODE = "reasoning_node"
CODING_NODE = "coding_node"
SOP_TOOL = "sop_tool"
TELEMETRY_TOOL = "telemetry_tool"
BEST_EFFORT = "synthesize_best_effort"
SYNTHESIS_NODE = "synthesis_node"


def _router(state: DiagnosticState) -> Literal["sop_tool", "telemetry_tool", "coding_node", "__end__"]:
    action = state.get("next_action")
    allowed = {CODING_NODE, SOP_TOOL, TELEMETRY_TOOL, END}
    if action in allowed:
        return action
    raise ValueError(f"invalid next_action: {action}")


def build_reasoning_graph():
    graph = StateGraph(DiagnosticState)
    graph.add_node(REASONING_NODE, run_reasoning_node)
    graph.add_node(SOP_TOOL, ToolNode([retrieve_sop]))
    graph.add_node(TELEMETRY_TOOL, ToolNode([get_relevant_telemetry]))
    graph.add_node(CODING_NODE, run_code_expert_node)
    graph.add_edge(START, REASONING_NODE)
    graph.add_edge(SOP_TOOL, REASONING_NODE)
    graph.add_edge(TELEMETRY_TOOL, REASONING_NODE)
    graph.add_edge(CODING_NODE, REASONING_NODE)
    # Conditional routing from reasoning (code expert, telemetry, or diagnosis)
    
    graph.add_conditional_edges(
        REASONING_NODE,
        _router,
        {
            SOP_TOOL: SOP_TOOL,
            TELEMETRY_TOOL: TELEMETRY_TOOL,
            CODING_NODE: CODING_NODE,
            END: END,
        },
    )
    return graph.compile()