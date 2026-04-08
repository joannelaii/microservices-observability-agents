from typing import Literal

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from common.state import DiagnosticState
from nodes.reasoning import run_filter_node, run_reasoning_node
from nodes.nodes import run_coding_agent_node
from tools.sop import retrieve_sop
from tools.telemetry import get_relevant_telemetry

REASONING_NODE = "reasoning_node"
FILTER_NODE = "filter_node"
CODING_NODE = "coding_node"
SOP_TOOL = "sop_tool"
TELEMETRY_TOOL = "telemetry_tool"
BEST_EFFORT = "synthesize_best_effort"
SYNTHESIS_NODE = "synthesis_node"
TOOLS_NODE = "tools_node"

_REASONING_TOOLS = [retrieve_sop, get_relevant_telemetry]
_MAX_REASONING_STEPS = 5


def _router(state: DiagnosticState) -> Literal["tools_node", "coding_node", "synthesis_node", "__end__"]:
    step_count = int(state.get("reasoning_step_count", 0) or 0)
    messages = state.get("reasoning_messages") or []
    coding_task = (state.get("coding_task") or "").strip()

    if not messages or is_diagnosed(state):
        return SYNTHESIS_NODE

    if coding_task:
        if step_count >= _MAX_REASONING_STEPS:
            return SYNTHESIS_NODE
        return CODING_NODE

    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        if step_count >= _MAX_REASONING_STEPS:
            return SYNTHESIS_NODE
        return TOOLS_NODE

    return SYNTHESIS_NODE


def is_diagnosed(state: DiagnosticState) -> bool:
    text = (state.get("reasoning_output") or "").strip()
    if not text:
        return False
    upper = text.upper()
    if "VERDICT: ROOT_CAUSE_FOUND" in upper:
        return True
    if "VERDICT: BEST_EFFORT" in upper:
        return True
    
    return False


def build_reasoning_graph():
    graph = StateGraph(DiagnosticState)
    graph.add_node(REASONING_NODE, run_reasoning_node)
    graph.add_node(CODING_NODE, run_coding_agent_node)
    graph.add_node(TOOLS_NODE, ToolNode(_REASONING_TOOLS, messages_key="reasoning_messages"))
    graph.add_node(FILTER_NODE, run_filter_node)

    graph.add_edge(START, REASONING_NODE)
    graph.add_conditional_edges(
        REASONING_NODE,
        _router,
        {
            TOOLS_NODE: TOOLS_NODE,
            CODING_NODE: CODING_NODE,
            SYNTHESIS_NODE: END,
            END: END,
        },
    )
    graph.add_edge(TOOLS_NODE, FILTER_NODE)
    graph.add_edge(FILTER_NODE, REASONING_NODE)
    graph.add_edge(CODING_NODE, REASONING_NODE)
    return graph.compile()
